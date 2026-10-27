"""Resolution-independent functional motion templates; customize content in JSON."""
from functools import lru_cache
import math
from PIL import Image, ImageDraw, ImageFont

def ease(u):u=max(0,min(1,u));return u*u*(3-2*u)

@lru_cache(maxsize=40)
def font(path,size):return ImageFont.truetype(path,max(8,int(size)))

def opacity(layer,amount):
    if amount>=.999:return layer
    layer=layer.copy();layer.putalpha(layer.getchannel('A').point(lambda v:round(v*max(0,amount))));return layer

def draw_overlay(item,u,size,font_path,theme,anchors=None):
    w,h=size;s=min(w/1920,h/1080)
    im=Image.new('RGBA',size);d=ImageDraw.Draw(im)
    color=item.get('color',theme.get('text','#eceee5'))
    accent=theme.get('accent','#9fc5ab');muted=theme.get('muted','#a0ada4')
    def xy(p):return (p[0]*w,p[1]*h)
    def text(p,value,px=52,fill=None,anchor=None):
        d.text(xy(p),str(value),font=font(font_path,px*s),fill=fill or color,anchor=anchor)
    kind=item.get('type','title')
    if kind=='text-workflow':
        split=max(.1,min(.9,item.get('typing_fraction',.48)))
        child=dict(item,_no_fade=True)
        child['type']='typewriter' if u<split else 'duplicate-undo'
        phase=u/split if u<split else (u-split)/(1-split)
        im=draw_overlay(child,phase,size,font_path,theme,anchors)
    elif kind=='title':
        text(item.get('position',[.06,.08]),item.get('text',''),item.get('size',56))
        if item.get('subtitle'):text([.061,.17],item['subtitle'],25,muted)
    elif kind in ['typewriter','duplicate-undo']:
        box=item.get('box',[.11,.32,.89,.70]);x0,y0,x1,y1=box
        d.rounded_rectangle((*xy((x0,y0)),*xy((x1,y1))),radius=20*s,
                            fill=theme.get('surface','#132219'),outline=theme.get('border','#38503e'),width=max(1,round(s)))
        value=item.get('text','Your product in action.');px=item.get('size',65)
        f=font(font_path,px*s);max_width=(x1-x0-.06)*w
        while d.textlength(value,font=f)>max_width and px>18:px-=1;f=font(font_path,px*s)
        x,y=xy((x0+.03,y0+.11))
        if kind=='typewriter':
            typed=value[:min(len(value),int(ease(min(1,u/.78))*len(value)))];d.text((x,y),typed,font=f,fill=color)
            cx=x+d.textlength(typed,font=f)+5*s
            if u<.90:d.rectangle((cx,y+8*s,cx+3*s,y+px*s),fill=accent)
            wave_y=y1*h+95*s
            for k in range(35):
                height=(8+55*abs(math.sin(k*.6+u*45)))*(1-ease((u-.82)/.16))
                xx=w*.5+(k-17)*14*s
                d.rounded_rectangle((xx-2*s,wave_y-height*s/2,xx+2*s,wave_y+height*s/2),radius=2*s,fill=accent)
        else:
            selected=ease((u-.08)/.12)*(1-ease((u-.37)/.07))
            if selected:
                highlight=Image.new('RGBA',size);hd=ImageDraw.Draw(highlight)
                hd.rounded_rectangle((x-7*s,y-4*s,x+d.textlength(value,font=f)+7*s,y+px*s+12*s),radius=7*s,fill=accent)
                im.alpha_composite(opacity(highlight,selected*.35));d=ImageDraw.Draw(im)
            d.text((x,y),value,font=f,fill=color)
            pasted=ease((u-.40)/.10)*(1-ease((u-.76)/.12))
            if pasted>0:
                clone=Image.new('RGBA',size);cd=ImageDraw.Draw(clone)
                cd.text((x,y+px*s*1.65*ease((u-.40)/.10)),value,font=f,fill=color)
                im.alpha_composite(opacity(clone,pasted));d=ImageDraw.Draw(im)
            state=item.get('actions',['Select','Copy','Paste','Undo'])
            index=0 if u<.25 else 1 if u<.4 else 2 if u<.76 else 3
            text([x0+.03,y1-.055],state[index],23,accent)
    elif kind=='progress':
        value=item.get('from',0)+(item.get('to',100)-item.get('from',0))*ease(u)
        text([.5,.42],f'{value:.0f}{item.get("suffix","%")}',110,color,'mm')
        x0,y=xy((.22,.59));x1=w*.82
        d.rounded_rectangle((x0,y-4*s,x1,y+4*s),radius=4*s,fill=theme.get('border','#38503e'))
        end=x0+(x1-x0)*max(0,min(1,value/100))
        if end>x0:d.rounded_rectangle((x0,y-4*s,end,y+4*s),radius=4*s,fill=accent)
        text([.5,.72],item.get('label',''),28,accent,'mm')
    elif kind=='scroll':
        clip=Image.new('RGBA',(round(w*.76),round(h*.46)));cd=ImageDraw.Draw(clip)
        lines=item.get('lines',['First feature','The product responds','Result confirmed'])
        shift=ease(u)*h*.22
        for j,value in enumerate(lines):cd.text((8*s,j*115*s-shift),value,font=font(font_path,44*s),fill=color)
        im.alpha_composite(clip,(round(w*.12),round(h*.32)))
    elif kind=='carrier':
        def location(v):
            if isinstance(v,str):
                if v not in (anchors or {}):raise ValueError('Unknown projected anchor: '+v)
                return anchors[v]
            return v
        a=location(item.get('from',[.2,.5]));b=location(item.get('to',[.8,.5]));q=ease(u)
        cx,cy=xy([a[0]+(b[0]-a[0])*q,a[1]+(b[1]-a[1])*q])
        radius=(item.get('radius_from',.02)+(item.get('radius_to',.10)-item.get('radius_from',.02))*q)*min(w,h)
        if item.get('shape','ring')=='line':
            d.rounded_rectangle((cx-radius,cy-2*s,cx+radius,cy+2*s),radius=2*s,fill=accent)
        else:d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),outline=accent,width=max(1,round(3*s)))
    else:raise ValueError('Unknown overlay type: '+kind)
    # Entry/exit are normalized to item duration; these are presentation fades,
    # not proof that two unrelated shots form a seamless transition.
    edge=max(.0001,float(item.get('fade_fraction',.12)))
    return im if item.get('_no_fade') else opacity(im,ease(u/edge)*ease((1-u)/edge))
