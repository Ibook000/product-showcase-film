# 项目配置与命令

## 文件与依赖

复制 `assets/project-template.json` 或 `assets/functional-project.json` 到独立工作目录。所有素材、字体、依赖文件与输出路径相对该 JSON 的目录解析，脚本位置不影响项目路径。`tools` 可写可执行文件名、相对路径或绝对路径；也支持对应的 `*_BIN` 环境变量与 PATH。不要把其他机器的绝对路径写进共享模板。

Python 3.10+；`scripts/requirements.txt` 为 Pillow、numpy。FFmpeg/FFprobe 需可执行；原生模型渲染使用 Blender 4.2+。示例都不需要账户、API 密钥、旧项目文件或其他技能。不要把 `.env`、模型权重、私人录屏或真实产品模型塞入技能包。

## 字段

| 字段 | 语义 |
|---|---|
| `format` | 偶数宽高、FPS、`duration_beats`；画幅与节奏只是可改参数 |
| `rhythm` | BPM、首拍偏移秒 `offset_seconds`、动作重音拍列表 `events` |
| `asset.source` | `.blend/.glb/.gltf/.obj/.fbx/.stl` 模型文件；没有真实模型时不填假路径来声称成功 |
| `asset.demo` | 仅为管线验证生成三个原始几何体，必须明确是演示资产 |
| `asset.include/exclude` | 通配符选择产品网格，用于包围盒；不删除场景中其他支持对象 |
| `asset.dependencies` | 外链纹理、MTL 等影响渲染的文件，加入缓存指纹；`inspect` 输出外链图片供核查 |
| `asset.source_frame` | 原模型保留的姿态帧，默认 1；绑定动画或复杂资产需适配器 |
| `asset.reuse_lighting` | `.blend` 默认保留原灯光；导入交换格式默认添加基本布光，可显式覆盖 |
| `camera` | perspective/orthographic、lens_mm、按拍递增的相机关键帧 |
| `motions` | 各组明确对象选择器与位移/局部欧拉旋转关键帧；不猜测对象角色 |
| `anchors` | 名称到产品归一化三维点或对象名称的映射；投影输出为画幅比例坐标 |
| `visuals` | 可选 model/image/video 层，按拍定义范围；无此字段且有模型时默认全时段显示模型 |
| `overlays` | 功能图形与标题，各有 type、start_beat、end_beat 与内容参数 |
| `style` | 字体文件与颜色；默认色板是示例，不是统一产品风格 |
| `audio` | mode 为 none/file/synth；文件模式用 source，内置 synth 仅为原创电子鼓点示例 |
| `render` | EEVEE 样本数、源渲染百分比，输出分辨率与源渲染分辨率分开记录 |
| `output_dir` | 项目内独立输出目录，原始输入不得放在这里 |
| `provenance` | 当前模型、视频、功能依据与生成素材的真实来源说明 |

## 坐标与动画

产品所选网格包围盒中心为原点，最长边为 span。相机 target、零件 translate 和数值型三维锚点使用 span 归一化的世界坐标，不依赖源模型是毫米还是米。归一化只用于控制，不改源几何。

相机关键帧字段：beat、target:[x,y,z]、distance、azimuth、elevation；正交模式还使用 ortho_scale。默认 smoothstep，目的关键帧可写 `ease:"linear"`。角度按给定数值直接插值，跨 ±180° 时应显式展开角度，避免意外长路径旋转。

motions 每组使用 `objects:["ExactName", "PartPrefix*"]`，关键帧含 beat、translate:[x,y,z]、rotate_degrees:[rx,ry,rz]。位移为世界偏移，旋转围绕对象现有原点按局部欧拉角增加。不要同时选择父级与其子级，也不要让两个运动组匹配同一对象；脚本会拒绝。需要特定支点时在任务适配器中建立可验证的支点，不强行绕错误原点旋转。

visuals 图像与视频支持 source、fit:"contain"|"cover"、zoom:[start,end]、fade_beats；视频另有 source_start_seconds。两个媒体层需要交叉淡化时必须让时间范围重叠。基础淡化只改变透明度，语义匹配仍由创作者负责。

照片和视频层的字段是 `kind`，覆盖层才使用 `type`。下面是无模型的素材项目片段，不要求 Blender；将相对路径替换为工作目录内的真实文件：

```json
{
  "asset": {"source": null, "demo": false},
  "visuals": [
    {"kind": "image", "source": "assets/product-front.jpg", "start_beat": 0, "end_beat": 9, "fit": "contain", "zoom": [1, 1.04], "fade_beats": 1},
    {"kind": "video", "source": "assets/product-use.mp4", "source_start_seconds": 0, "start_beat": 8, "end_beat": 16, "fit": "contain", "fade_beats": 1}
  ]
}
```

功能覆盖层使用 0–1 画幅坐标；详情见 [功能动效](functional-graphics.md)。carrier.from/to 可为 [x,y]，或已配置的三维锚点名称。图片缩放仅是后期二维变换，不改变原相机。

## 拍点

`time = offset_seconds + beat * 60 / BPM`。视频帧与音频采样分别从绝对时间取整，不累加已取整的单拍帧数。plan 保存每个事件的 frame、sample 与误差。例如 24 FPS、120 BPM 为每拍 12 帧；128 BPM 则不是整数帧拍长，时间线仍应正确量化。

内置 synth 按 BPM 生成示例鼓点，并在 events 放交互音。真实歌曲需要人工或工具确认真实首拍与变速拍点；当前基础脚本不自动分析变速歌曲。改为外部音乐时将实际拍点写入任务时间线，不假定整曲固定 BPM。

## 命令与缓存

- init project.json：真实素材模板；--demo：完全独立的原始几何示例。遇到已有文件拒绝覆盖。
- plan：不要求媒体或 Blender 齐全，先计算事件的拍/帧/采样网格。
- check：检查输入路径、工具与字体文件。字体存在不代表中文字符覆盖正确。
- inspect：读取模型并输出对象、边界和外链图片清单，不渲染产品视频。
- preview --preview-beats 0,2,4：渲染选中关键帧并合成功能覆盖，便于先查难点。
- render：原生模型缓存、合成、声音、最终编码与自动验证。
- finish：复用现有原生画面，修改覆盖或音乐；模型缓存缺失会报错，不无限等待。
- verify：完整解码、尺寸/帧数/时长、最终编码音频 true peak；视觉检查仍需执行。

原生缓存签名含模型与显式依赖的路径/大小/修改时间、相机、运动、锚点、渲染格式、渲染脚本摘要和 Blender 可执行文件属性。文字和配乐改变不会改变原生画面签名；合成缓存另含覆盖层、字体、脚本与素材属性。素材属性不是内容哈希：来源可能被保留原属性覆盖时，强制用新缓存目录或内容摘要。

帧与视频先写 partial 再原子替换。命令有超时，不后台无限等待；失败日志保存在输出目录。技能不会自行安装二进制程序、下载模型或发布结果。

输出包括 product-showcase.mp4、preview/、beat-plan.json（调用 plan 后）、provenance.json、缓存及 verification/report.json。重用同一个任务输出目录会替换该目录中的成片；需要保留版本时使用新的 output_dir，原始素材不可放进输出目录。
