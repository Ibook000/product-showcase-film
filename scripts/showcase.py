"""Portable product-film CLI. Paths are relative to the project JSON, not this skill."""
import argparse, hashlib, json, math, os, re, shutil, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
FLAGS={'creationflags':0x08000000} if os.name=='nt' else {}

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.partial')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
def stamp(path):
    p=Path(path);stat=p.stat()
    return dict(path=str(p),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns)
def tool(name,cfg):
    candidate=cfg.get('tools',{}).get(name) or os.environ.get(name.upper()+'_BIN') or name
    resolved=shutil.which(str(candidate))
    if not resolved and Path(str(candidate)).is_file():resolved=str(Path(candidate).resolve())
    if not resolved:raise ValueError(f'{name} not found; set tools.{name}, {name.upper()}_BIN, or PATH')
    return resolved

def find_font(cfg):
    supplied=cfg.get('style',{}).get('font')
    if supplied and not Path(supplied).is_file():raise ValueError('Configured font does not exist: '+supplied)
    candidates=[supplied] if supplied else []
    candidates += ['C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/arial.ttf',
      '/System/Library/Fonts/PingFang.ttc','/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
      '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for p in candidates:
        if p and Path(p).is_file():return str(Path(p).resolve())
    raise ValueError('No font found; set style.font to an installed font file supporting your text')

def load(path,args):
    path=Path(path).expanduser().resolve();cfg=json.loads(path.read_text(encoding='utf-8'))
    root=path.parent;cfg['_project']=str(path)
    def resolve(value):return str((root/Path(value).expanduser()).resolve())
    cfg['_output']=resolve(cfg.get('output_dir','output'))
    cfg.setdefault('tools',{})
    for name in ['blender','ffmpeg','ffprobe']:
        if getattr(args,name,None):cfg['tools'][name]=getattr(args,name)
        elif name in cfg['tools'] and ('/' in cfg['tools'][name] or '\\' in cfg['tools'][name]):cfg['tools'][name]=resolve(cfg['tools'][name])
    cfg.setdefault('asset',{});cfg.setdefault('style',{});cfg.setdefault('rhythm',{})
    cfg['rhythm'].setdefault('offset_seconds',0)
    cfg.setdefault('audio',{'mode':'none'});cfg.setdefault('render',{})
    cfg.setdefault('camera',{'projection':'perspective','keyframes':[
      {'beat':0,'target':[0,0,0],'distance':2.8,'azimuth':-100,'elevation':32},
      {'beat':cfg['format']['duration_beats'],'target':[0,0,0],'distance':2.3,'azimuth':-80,'elevation':38}]})
    for owner,key in [(cfg['asset'],'source'),(cfg['style'],'font'),(cfg['audio'],'source')]:
        if owner.get(key):owner[key]=resolve(owner[key])
    cfg['asset']['dependencies']=[resolve(p) for p in cfg['asset'].get('dependencies',[])]
    if 'visuals' not in cfg:
        cfg['visuals']=[dict(kind='model',start_beat=0,end_beat=cfg['format']['duration_beats'])] if cfg['asset'].get('source') or cfg['asset'].get('demo') else []
    for index,visual in enumerate(cfg['visuals']):
        if not isinstance(visual,dict) or visual.get('kind') not in ['model','image','video']:
            raise ValueError(f'visuals[{index}].kind must be model, image, or video; use type only for overlays')
        if visual.get('source'):visual['source']=resolve(visual['source'])
    cfg['_has_model']=any(v['kind']=='model' for v in cfg['visuals'])
    fmt=cfg['format'];bpm=cfg['rhythm']['bpm'];fps=fmt['fps']
    if not all(isinstance(v,(float,int)) and math.isfinite(v) and v>0 for v in [bpm,fps,fmt['width'],fmt['height'],fmt['duration_beats']]):
        raise ValueError('BPM, FPS, dimensions and duration_beats must be positive finite numbers')
    if int(fmt['width'])%2 or int(fmt['height'])%2:raise ValueError('H.264 dimensions must be even')
    if any(int(fmt[k])!=fmt[k] for k in ['width','height']):raise ValueError('Dimensions must be integers')
    cfg['_frames']=round((cfg['rhythm']['offset_seconds']+fmt['duration_beats']*60/bpm)*fps)
    if cfg['_frames']<1:raise ValueError('Timeline has no frames')
    cfg['_duration']=cfg['_frames']/fps
    cfg['_font']=find_font(cfg) if args.command!='plan' else cfg['style'].get('font')
    return cfg

def moment(cfg,beat):return cfg['rhythm']['offset_seconds']+beat*60/cfg['rhythm']['bpm']
def frame_at(cfg,beat):return round(moment(cfg,beat)*cfg['format']['fps'])

def validate(cfg):
    tool('ffmpeg',cfg);tool('ffprobe',cfg)
    paths=[]
    if cfg['_has_model']:
        tool('blender',cfg)
        if not cfg['asset'].get('source') and not cfg['asset'].get('demo'):raise ValueError('Model visual needs asset.source; demo must be explicit')
        if cfg['asset'].get('source'):paths.append(cfg['asset']['source'])
        keys=cfg['camera']['keyframes']
        if not keys:raise ValueError('Camera keyframes cannot be empty')
        if any(a['beat']>=b['beat'] for a,b in zip(keys,keys[1:])):raise ValueError('Camera beats must increase strictly')
        for motion in cfg.get('motions',[]):
            keys=motion['keyframes']
            if not keys or not motion.get('objects'):raise ValueError('Motion requires object selectors and keyframes')
            if any(a['beat']>=b['beat'] for a,b in zip(keys,keys[1:])):raise ValueError('Motion beats must increase strictly')
    paths+=cfg['asset'].get('dependencies',[])
    for item in cfg['visuals']+cfg.get('overlays',[]):
        if item.get('end_beat',0)<=item.get('start_beat',0):raise ValueError('Each visual/overlay needs end_beat > start_beat')
        if item.get('source'):paths.append(item['source'])
    if cfg['audio'].get('mode')=='file':paths.append(cfg['audio']['source'])
    for p in paths:
        if not Path(p).is_file():raise ValueError('Missing input: '+p)
        if Path(p).resolve().is_relative_to(Path(cfg['_output'])):raise ValueError('Source input cannot be inside the generated output directory: '+p)
    return paths

def plan(cfg):
    events=[]
    for index,beat in enumerate(cfg['rhythm'].get('events',[])):
        second=moment(cfg,beat);frame=round(second*cfg['format']['fps']);sample=round(second*cfg['audio'].get('sample_rate',48000))
        events.append(dict(event=index,beat=beat,seconds=second,frame=frame,sample=sample,
          video_error_ms=(frame/cfg['format']['fps']-second)*1000))
    return dict(frames=cfg['_frames'],duration_seconds=cfg['_duration'],bpm=cfg['rhythm']['bpm'],
        fps=cfg['format']['fps'],event_grid=events,maximum_grid_error_ms=max([abs(v['video_error_ms']) for v in events] or [0]))

def cache(cfg):
    out=Path(cfg['_output']);out.mkdir(parents=True,exist_ok=True)
    source=cfg['asset'].get('source')
    signature=dict(asset=cfg['asset'],source=stamp(source) if source else None,
       dependencies=[stamp(p) for p in cfg['asset'].get('dependencies',[])],camera=cfg['camera'],
       motions=cfg.get('motions',[]),anchors=cfg.get('anchors',{}),format=cfg['format'],
       rhythm={k:cfg['rhythm'][k] for k in ['bpm','offset_seconds']},render=cfg['render'],blender=stamp(tool('blender',cfg)),
       renderer_sha256=hashlib.sha256((HERE/'blender_scene.py').read_bytes()).hexdigest())
    folder=out/'intermediate'/'model'/digest(signature);folder.mkdir(parents=True,exist_ok=True)
    cfg['_model_cache']=str(folder)
    write_json(folder/'resolved.json',cfg);write_json(folder/'signature.json',signature)
    return folder

def run(args,log,cfg):
    log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('w',encoding='utf-8') as f:
        try:p=subprocess.run([str(v) for v in args],stdout=f,stderr=f,timeout=cfg.get('tools',{}).get('timeout_seconds',7200),**FLAGS)
        except subprocess.TimeoutExpired as e:raise RuntimeError('Operation timed out; inspect '+str(log)) from e
    if p.returncode:raise RuntimeError(log.read_text(encoding='utf-8',errors='replace')[-3000:])

def model_render(cfg,frames=None,inspect_only=False):
    folder=cache(cfg);cmd=[tool('blender',cfg),'-b','--disable-autoexec','--python',HERE/'blender_scene.py','--','--config',folder/'resolved.json']
    if inspect_only:cmd+=['--inspect']
    elif frames is not None:cmd+=['--frames',','.join(str(v) for v in frames)]
    print('BLENDER_START '+str(folder),flush=True);run(cmd,folder/'blender.log',cfg)
    print('BLENDER_DONE',flush=True)
    return folder

def prepared(cfg):
    from PIL import Image,ImageOps
    fmt=cfg['format'];w,h=fmt['width'],fmt['height'];out=Path(cfg['_output']);sources={}
    for index,item in enumerate(cfg['visuals']):
        kind=item['kind']
        if kind=='image':
            im=Image.open(item['source']).convert('RGBA');sources[index]=im
        elif kind=='video':
            count=max(1,frame_at(cfg,item['end_beat'])-frame_at(cfg,item['start_beat']))
            key=digest(dict(source=stamp(item['source']),item=item,format=fmt))
            folder=out/'intermediate'/'media'/key;folder.mkdir(parents=True,exist_ok=True)
            if not (folder/'complete.json').exists():
                filters=f"fps={fmt['fps']},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,tpad=stop_mode=clone:stop_duration={count/fmt['fps']}"
                run([tool('ffmpeg',cfg),'-y','-v','error','-ss',item.get('source_start_seconds',0),'-i',item['source'],
                     '-an','-vf',filters,'-frames:v',count,'-start_number','0',folder/'%06d.png'],folder/'extract.log',cfg)
                if not (folder/f'{count-1:06d}.png').exists():raise ValueError('Video produced too few frames; inspect source_start_seconds')
                write_json(folder/'complete.json',{'frames':count})
            sources[index]=folder
        elif kind!='model':raise ValueError('Unknown visual kind: '+kind)
    return sources

def picture(cfg,frame,sources,metadata):
    from PIL import Image,ImageOps
    from graphics import draw_overlay,opacity,ease
    fmt=cfg['format'];size=(fmt['width'],fmt['height']);beat=(frame/fmt['fps']-cfg['rhythm']['offset_seconds'])*cfg['rhythm']['bpm']/60
    bg=cfg['style'].get('background','#0a140e');im=Image.new('RGBA',size,bg)
    for index,item in enumerate(cfg['visuals']):
        start,end=item['start_beat'],item['end_beat']
        if not start<=beat<end:continue
        u=(beat-start)/(end-start);kind=item['kind']
        if kind=='model':p=Path(cfg['_model_cache'])/f'{frame:06d}.png';layer=Image.open(p).convert('RGBA')
        elif kind=='video':p=sources[index]/f'{max(0,frame-frame_at(cfg,start)):06d}.png';layer=Image.open(p).convert('RGBA')
        else:layer=sources[index].copy()
        if item.get('fit','contain')=='cover':layer=ImageOps.fit(layer,size,method=Image.Resampling.LANCZOS)
        else:
            layer=ImageOps.contain(layer,size,method=Image.Resampling.LANCZOS);canvas=Image.new('RGBA',size);canvas.alpha_composite(layer,((size[0]-layer.width)//2,(size[1]-layer.height)//2));layer=canvas
        zoom=item.get('zoom',[1,1]);z=zoom[0]+(zoom[1]-zoom[0])*ease(u)
        if z<=0:raise ValueError('Zoom must be positive')
        if abs(z-1)>.00001:
            w,h=size;cw,ch=w/z,h/z
            layer=layer.transform(size,Image.Transform.EXTENT,((w-cw)/2,(h-ch)/2,(w+cw)/2,(h+ch)/2),Image.Resampling.BICUBIC)
        fade=item.get('fade_beats',0)
        strength=min(1,(beat-start)/fade,(end-beat)/fade) if fade>0 else 1
        im.alpha_composite(opacity(layer,ease(strength)))
    anchors=metadata.get(frame,{}).get('anchors',{})
    for item in cfg.get('overlays',[]):
        a,b=item['start_beat'],item['end_beat']
        if a<=beat<b:im.alpha_composite(draw_overlay(item,(beat-a)/(b-a),size,cfg['_font'],cfg['style'],anchors))
    return im.convert('RGB')

def metadata(cfg,preview=False):
    if not cfg['_has_model']:return {}
    folder=Path(cfg['_model_cache']);p=folder/'metadata.json'
    if not p.exists():p=folder/'preview-metadata.json'
    if not p.exists():return {}
    return {v['frame']:v for v in json.loads(p.read_text(encoding='utf-8'))}

def preview(cfg,args):
    beats=[float(v) for v in args.preview_beats.split(',')] if args.preview_beats else [cfg['format']['duration_beats']*v for v in [0,.25,.5,.75,.98]]
    frames=sorted(set(max(0,min(cfg['_frames']-1,frame_at(cfg,b))) for b in beats))
    if cfg['_has_model']:model_render(cfg,frames)
    sources=prepared(cfg);records=metadata(cfg,True)
    folder=Path(cfg['_output'])/'preview';folder.mkdir(exist_ok=True)
    for f in frames:picture(cfg,f,sources,records).save(folder/f'{f:06d}.jpg',quality=92)
    print('PREVIEWS '+str(folder),flush=True)

def finish(cfg):
    from PIL import Image
    sources=prepared(cfg);records=metadata(cfg);fmt=cfg['format'];out=Path(cfg['_output'])
    fingerprint=dict(config=cfg,inputs=[stamp(p) for p in validate(cfg)],
        scripts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')},font=stamp(cfg['_font']))
    folder=out/'intermediate'/'composite'/digest(fingerprint);folder.mkdir(parents=True,exist_ok=True)
    video=folder/'picture.mp4'
    if not video.exists():
        temporary=folder/'picture.partial.mp4'
        with (folder/'encode.log').open('w',encoding='utf-8') as log:
            p=subprocess.Popen([tool('ffmpeg',cfg),'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f"{fmt['width']}x{fmt['height']}",
                '-r',str(fmt['fps']),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf',str(cfg.get('encoding',{}).get('crf',18)),
                '-pix_fmt','yuv420p','-threads','4',str(temporary)],stdin=subprocess.PIPE,stdout=log,stderr=log,**FLAGS)
            try:
                for f in range(cfg['_frames']):
                    if cfg['_has_model'] and not (Path(cfg['_model_cache'])/f'{f:06d}.png').exists():raise ValueError('Model cache incomplete: run render, not finish')
                    p.stdin.write(picture(cfg,f,sources,records).tobytes())
                    if f%48==0:print('COMPOSE',f,cfg['_frames'],flush=True)
                p.stdin.close()
                if p.wait(timeout=120):raise RuntimeError('Encoder failed; inspect '+str(folder/'encode.log'))
            except BaseException:p.kill();p.wait();raise
        os.replace(temporary,video)
    audio=cfg['audio'];mode=audio.get('mode','none');wav=None
    if mode=='synth':
        from music import synthesize
        wav=synthesize(folder/'music.wav',cfg['_duration'],cfg['rhythm']['bpm'],audio.get('sample_rate',48000),audio.get('seed',7),
                       cfg['rhythm']['offset_seconds'],[moment(cfg,b) for b in cfg['rhythm'].get('events',[])])
    elif mode=='file':wav=Path(audio['source'])
    elif mode!='none':raise ValueError('Unknown audio.mode: '+mode)
    final=out/'product-showcase.mp4';temp=out/'product-showcase.partial.mp4'
    command=[tool('ffmpeg',cfg),'-y','-v','error','-i',video]
    if wav:
        command+=['-i',wav,'-map','0:v:0','-map','1:a:0','-c:v','copy','-af',f"loudnorm=I={audio.get('lufs',-16)}:TP={audio.get('master_peak',-2.5)}:LRA=7,apad",
                  '-c:a','aac','-b:a','256k','-ar',str(audio.get('sample_rate',48000))]
    else:command+=['-map','0:v:0','-an','-c:v','copy']
    command+=['-t',str(cfg['_duration']),'-movflags','+faststart',temp]
    run(command,folder/'mux.log',cfg);os.replace(temp,final)
    write_json(out/'provenance.json',dict(input_sources=[stamp(p) for p in validate(cfg)],
      source_render_percentage=cfg['render'].get('percentage',100),output_dimensions=[fmt['width'],fmt['height']],
      demo_asset=cfg['asset'].get('demo',False),functional_graphics_present=bool(cfg.get('overlays')),
      functional_graphics_are_illustrations=True,generative_video_service_invoked_by_this_renderer=False,
      declared_visual_provenance=cfg.get('provenance',{}),note='Record actual tool and output if generated video is used.'))
    print('VIDEO '+str(final),flush=True)
    return final

def verify(cfg,path=None):
    final=Path(path) if path else Path(cfg['_output'])/'product-showcase.mp4'
    raw=subprocess.check_output([tool('ffprobe',cfg),'-v','error','-show_streams','-show_format','-of','json',str(final)],**FLAGS)
    data=json.loads(raw);v=next(s for s in data['streams'] if s['codec_type']=='video');fmt=cfg['format']
    if (v['width'],v['height'])!=(fmt['width'],fmt['height']):raise ValueError('Wrong output dimensions')
    if abs(float(data['format']['duration'])-cfg['_duration'])>max(.06,1/fmt['fps']):raise ValueError('Wrong output duration')
    if int(v.get('nb_frames',cfg['_frames']))!=cfg['_frames']:raise ValueError('Wrong output frame count')
    folder=Path(cfg['_output'])/'verification';folder.mkdir(parents=True,exist_ok=True)
    run([tool('ffmpeg',cfg),'-v','error','-xerror','-i',final,'-f','null','-'],folder/'decode.log',cfg)
    result=dict(full_decode_passed=True,dimensions=[v['width'],v['height']],frames=v.get('nb_frames'),duration=float(data['format']['duration']),
       plan=plan(cfg),visual_review='Required: automatic decoding and frame statistics do not establish seamlessness or correctness of product claims.')
    if any(s['codec_type']=='audio' for s in data['streams']):
        p=subprocess.run([tool('ffmpeg',cfg),'-hide_banner','-i',str(final),'-af','ebur128=peak=true','-f','null','-'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',**FLAGS)
        if p.returncode:raise ValueError('Audio measurement failed')
        (folder/'audio-levels.log').write_text(p.stdout,encoding='utf-8')
        peaks=re.findall(r'Peak:\s+(-?[\d.]+) dBFS',p.stdout)
        if not peaks:raise ValueError('Could not measure encoded audio true peak')
        result['audio_true_peak_dbfs']=float(peaks[-1]);result['audio_peak_limit_dbfs']=cfg['audio'].get('verify_peak',-1)
        result['audio_peak_passed']=result['audio_true_peak_dbfs']<=result['audio_peak_limit_dbfs']
    write_json(folder/'report.json',result)
    if result.get('audio_peak_passed') is False:raise ValueError('Encoded audio exceeds peak limit: lower master_peak and rerun finish; model render is cached')
    print(json.dumps(result,ensure_ascii=False,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','check','plan','inspect','preview','render','finish','verify'])
    parser.add_argument('project',nargs='?',default='project.json')
    parser.add_argument('--demo',action='store_true');parser.add_argument('--preview-beats')
    for name in ['blender','ffmpeg','ffprobe']:parser.add_argument('--'+name)
    args=parser.parse_args()
    if args.command=='init':
        p=Path(args.project)
        if p.exists():raise FileExistsError('Project already exists: '+str(p))
        template=json.loads((HERE.parent/'assets'/'project-template.json').read_text(encoding='utf-8'))
        if args.demo:template=json.loads((HERE.parent/'assets'/'demo-project.json').read_text(encoding='utf-8'))
        write_json(p,template);print('CREATED '+str(p.resolve()));return
    cfg=load(args.project,args);out=Path(cfg['_output']);out.mkdir(parents=True,exist_ok=True)
    if args.command=='plan':write_json(out/'beat-plan.json',plan(cfg));print(json.dumps(plan(cfg),indent=2));return
    paths=validate(cfg)
    if cfg['_has_model']:cache(cfg)
    if args.command=='check':print(json.dumps(dict(inputs=paths,font=cfg['_font'],duration=cfg['_duration'],frames=cfg['_frames'],
        warning='Font discovery does not prove glyph coverage. Review CJK text and use the host image-inspection workflow.'),ensure_ascii=False,indent=2))
    elif args.command=='inspect':
        if not cfg['_has_model']:raise ValueError('No model visual to inspect')
        model_render(cfg,inspect_only=True)
    elif args.command=='preview':preview(cfg,args)
    elif args.command=='render':
        if cfg['_has_model']:model_render(cfg)
        finish(cfg);verify(cfg)
    elif args.command=='finish':finish(cfg);verify(cfg)
    elif args.command=='verify':verify(cfg)

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,FileNotFoundError,FileExistsError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);raise SystemExit(1)
