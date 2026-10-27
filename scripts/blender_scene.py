"""Run with Blender --background --python ... -- --config resolved.json."""
import argparse, fnmatch, json, math, os, sys
from pathlib import Path
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

def ease(u):u=max(0,min(1,u));return u*u*(3-2*u)
def at(keys,beat):
    if beat<=keys[0]['beat']:return keys[0]
    if beat>=keys[-1]['beat']:return keys[-1]
    for a,b in zip(keys,keys[1:]):
        if beat<=b['beat']:
            u=(beat-a['beat'])/(b['beat']-a['beat'])
            if b.get('ease','smooth')!='linear':u=ease(u)
            result={'beat':beat}
            for key in set(a)|set(b):
                if key in ['beat','ease']:continue
                x=a.get(key,b.get(key));y=b.get(key,a.get(key))
                if isinstance(x,list):result[key]=[v+(q-v)*u for v,q in zip(x,y)]
                elif isinstance(x,(int,float)):result[key]=x+(y-x)*u
                else:result[key]=x
            return result

def material(name,color,metal=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    node=m.node_tree.nodes.get('Principled BSDF');node.inputs['Base Color'].default_value=(*color,1)
    node.inputs['Metallic'].default_value=metal;node.inputs['Roughness'].default_value=.32
    return m

def cube(name,loc,scale,color):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);ob=bpy.context.object;ob.name=name;ob.dimensions=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    ob.data.materials.append(material(name+'Material',color))
    bevel=ob.modifiers.new('Showcase bevel','BEVEL');bevel.width=min(scale)*.13;bevel.segments=3
    ob.modifiers.new('Showcase normals','WEIGHTED_NORMAL');return ob

def load(config):
    asset=config['asset'];source=asset.get('source')
    if source:
        path=Path(source);ext=path.suffix.lower()
        if ext=='.blend':bpy.ops.wm.open_mainfile(filepath=str(path))
        else:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            if ext in ['.glb','.gltf']:bpy.ops.import_scene.gltf(filepath=str(path))
            elif ext=='.obj':bpy.ops.wm.obj_import(filepath=str(path))
            elif ext=='.fbx':bpy.ops.import_scene.fbx(filepath=str(path))
            elif ext=='.stl':bpy.ops.wm.stl_import(filepath=str(path))
            else:raise ValueError('Unsupported model format: '+ext)
    elif asset.get('demo'):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        cube('DemoBody',(0,0,.12),(1.6,.90,.24),(.15,.19,.17))
        cube('DemoInsert',(.36,0,.31),(.42,.42,.14),(.28,.43,.33))
        cube('DemoCover',(.36,0,.44),(.55,.55,.12),(.75,.77,.68))
    else:raise ValueError('Provide asset.source, or explicitly enable asset.demo')
    sc=bpy.context.scene
    sc.frame_set(int(asset.get('source_frame',1)))
    include=asset.get('include',[]);exclude=asset.get('exclude',[])
    meshes=[o for o in sc.objects if o.type=='MESH' and not o.hide_render
            and (not include or any(fnmatch.fnmatchcase(o.name,p) for p in include))
            and not any(fnmatch.fnmatchcase(o.name,p) for p in exclude)]
    if not meshes:raise ValueError('No visible meshes matched the product selection')
    corners=[o.matrix_world@Vector(v) for o in meshes for v in o.bound_box]
    low=Vector([min(p[j] for p in corners) for j in range(3)])
    high=Vector([max(p[j] for p in corners) for j in range(3)])
    center=(low+high)/2;span=max(high-low)
    if span<=0:raise ValueError('Product bounds have zero extent')
    info=dict(bounds_min=list(low),bounds_max=list(high),span=span,
        objects=[dict(name=o.name,dimensions=list(o.dimensions)) for o in meshes],
        external_images=[bpy.path.abspath(i.filepath) for i in bpy.data.images if i.filepath and not i.packed_file])
    return sc,meshes,center,span,low,info

def setup(config,sc,center,span,low):
    asset=config['asset']
    native_blend=bool(asset.get('source')) and Path(asset['source']).suffix.lower()=='.blend'
    if asset.get('demo') or not asset.get('reuse_lighting',native_blend):
        for ob in list(sc.objects):
            if ob.type=='LIGHT':ob.hide_render=True
        world=bpy.data.worlds.new('ShowcaseWorld');sc.world=world;world.use_nodes=True
        world.node_tree.nodes['Background'].inputs['Color'].default_value=(.06,.07,.065,1)
        world.node_tree.nodes['Background'].inputs['Strength'].default_value=.4
        for name,offset,energy,size,color in [
            ('Key',(-1.8,-2.5,3),950,3,(.90,.96,1)),
            ('Fill',(2,1.4,2),700,2,(1,.92,.8)),
            ('Rim',(-1,2,2),850,2,(.65,1,.8))]:
            data=bpy.data.lights.new('Showcase'+name,'AREA');data.energy=energy*span*span;data.shape='DISK';data.size=size*span;data.color=color
            ob=bpy.data.objects.new(data.name,data);sc.collection.objects.link(ob);ob.location=center+Vector(offset)*span
            ob.rotation_euler=(center-ob.location).to_track_quat('-Z','Y').to_euler()
        if asset.get('ground',True):
            bpy.ops.mesh.primitive_plane_add(size=20*span,location=(center.x,center.y,low.z-.008*span))
            bpy.context.object.name='ShowcaseGround';bpy.context.object.data.materials.append(material('ShowcaseGroundMaterial',(.015,.021,.017)))
    data=bpy.data.cameras.new('ShowcaseCamera');cam=bpy.data.objects.new('ShowcaseCamera',data)
    sc.collection.objects.link(cam);sc.camera=cam
    data.type='ORTHO' if config['camera'].get('projection')=='orthographic' else 'PERSP'
    data.lens=config['camera'].get('lens_mm',50);data.clip_start=max(span*.0001,1e-6);data.clip_end=span*1000
    fmt=config['format'];rend=config.get('render',{})
    sc.render.engine='BLENDER_EEVEE_NEXT';sc.eevee.taa_render_samples=int(rend.get('samples',24))
    sc.render.resolution_x=int(fmt['width']);sc.render.resolution_y=int(fmt['height'])
    sc.render.resolution_percentage=int(rend.get('percentage',100));sc.render.fps=round(fmt['fps']);sc.render.fps_base=round(fmt['fps'])/fmt['fps']
    sc.render.image_settings.file_format='PNG';sc.render.image_settings.color_mode='RGB';sc.render.image_settings.compression=3
    sc.render.use_persistent_data=True
    return cam

def main():
    argv=sys.argv[sys.argv.index('--')+1:];parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True);parser.add_argument('--inspect',action='store_true');parser.add_argument('--frames')
    args=parser.parse_args(argv);cfg=json.loads(Path(args.config).read_text(encoding='utf-8'))
    cache=Path(cfg['_model_cache']);cache.mkdir(parents=True,exist_ok=True)
    sc,meshes,center,span,low,info=load(cfg)
    (cache/'inspection.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.inspect:print('INSPECTION '+str(cache/'inspection.json'),flush=True);return
    cam=setup(cfg,sc,center,span,low)
    motions=[];allowed={o.name:o for o in sc.objects if o.type not in ['CAMERA','LIGHT']}
    animated={}
    for motion in cfg.get('motions',[]):
        matched=[o for name,o in allowed.items() if any(fnmatch.fnmatchcase(name,p) for p in motion['objects'])]
        if not matched:raise ValueError('No objects matched motion '+str(motion['objects']))
        motions.append((motion,matched))
        for ob in matched:
            if ob.name in animated:raise ValueError('Object matched multiple motion groups: '+ob.name)
            animated[ob.name]=ob
    # Animate explicit objects only. Scene reset must never undo the camera.
    originals={name:o.matrix_basis.copy() for name,o in animated.items()}
    for name,o in animated.items():
        p=o.parent
        while p:
            if p.name in animated:raise ValueError('Select a parent or its children, not both: '+name)
            p=p.parent
    count=cfg['_frames'];fps=cfg['format']['fps'];bpm=cfg['rhythm']['bpm'];offset=cfg['rhythm'].get('offset_seconds',0)
    frames=[int(v) for v in args.frames.split(',')] if args.frames else range(count)
    records=[]
    for index,frame in enumerate(frames):
        if not 0<=frame<count:raise ValueError('Frame outside timeline')
        beat=(frame/fps-offset)*bpm/60
        for name,ob in animated.items():ob.matrix_basis=originals[name].copy()
        bpy.context.view_layer.update()
        # Rigid motions are world translations plus local Euler offsets.
        for motion,objects in motions:
            state=at(motion['keyframes'],beat)
            move=Vector(state.get('translate',[0,0,0]))*span
            for ob in objects:
                world=ob.matrix_world.copy();world.translation+=move;ob.matrix_world=world
                angles=state.get('rotate_degrees',[0,0,0])
                for axis in range(3):ob.rotation_euler[axis]+=math.radians(angles[axis])
        state=at(cfg['camera']['keyframes'],beat)
        target=center+Vector(state.get('target',[0,0,0]))*span
        yaw=math.radians(state.get('azimuth',-90));elev=math.radians(state.get('elevation',35));r=state.get('distance',2.8)*span
        cam.location=target+Vector((r*math.cos(elev)*math.cos(yaw),r*math.cos(elev)*math.sin(yaw),r*math.sin(elev)))
        cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
        cam.data.ortho_scale=state.get('ortho_scale',2.1)*span
        bpy.context.view_layer.update()
        projected={}
        for name,anchor in cfg.get('anchors',{}).items():
            if isinstance(anchor,str):
                ob=bpy.data.objects.get(anchor)
                if not ob:raise ValueError('Unknown anchor object: '+anchor)
                world=ob.matrix_world@(sum((Vector(v) for v in ob.bound_box),Vector())/8) if ob.type=='MESH' else ob.matrix_world.translation
            else:world=center+Vector(anchor)*span
            q=world_to_camera_view(sc,cam,world);projected[name]=[q.x,1-q.y]
        record=dict(frame=frame,beat=beat,camera_position=list(cam.location),camera_target=list(target),anchors=projected,
                    animated_positions={name:list(o.matrix_world.translation) for name,o in animated.items()})
        records.append(record)
        output=cache/f'{frame:06d}.png'
        if not output.exists():
            temporary=cache/f'{frame:06d}.partial.png';sc.render.filepath=str(temporary)
            bpy.ops.render.render(write_still=True);os.replace(temporary,output)
        if index%24==0:print('RENDER_PROGRESS',index,len(frames),flush=True)
    (cache/('preview-metadata.json' if args.frames else 'metadata.json')).write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RENDER_COMPLETE '+str(cache),flush=True)

if __name__=='__main__':main()
