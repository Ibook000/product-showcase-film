# product-showcase-film

给 AI Agent 使用的通用产品展示视频 Skill。将三维模型、产品照片、视频和功能动效编排为可修改、可复演的展示视频。

适用于产品宣传、毕业设计展示和功能演示。支持实物与软件产品；不限定产品类型、配色、时长或音乐风格。

## 能做什么

| 场景 | 方法 |
| --- | --- |
| 外观与细节 | 原生三维取景、远近景变化、照片与视频编排 |
| 装配与拆卸 | 明确零件映射、独立运动曲线、复装与更换展示 |
| 功能说明 | 文字输入、选中、复制粘贴撤销、滚动与进度反馈 |
| 节奏与转场 | 绝对拍点量化、动作重音、共同元素和运动连续性 |
| 修改旧版 | 保留参考版本，按素材和配置签名复用缓存 |
| 导出与验证 | MP4、关键帧、来源记录、解码和编码后音频峰值检查 |

提供制作方法与基础脚本。任意产品的精细建模、复杂变形、物理模拟或生成式视频，需要当前 Agent 的相应工具和任务适配；不是一键替代全部创作工作。功能动效是示意，不冒充真实操作或性能测试。

## 给其他 AI 使用

下载本仓库，或复制整个目录到目标 Agent 的技能目录。让 AI 先读取 [SKILL.md](SKILL.md)，再按需读取相对引用；不依赖 Codex、特定插件、旧视频工程或账户。

可直接把下面的话和产品素材交给 AI：

```text
请读取 product-showcase-film/SKILL.md，并按这个技能制作产品展示视频。
产品与素材：……
重点展示：……
用途、画幅与时长：……
声音要求：……
先设计画面、动作和转场，验证关键片段后完成整片并保留工程。
```

支持技能调用的 Agent 可显式使用 `$product-showcase-film`。

## 安装示例

以使用 `~/.codex/skills` 的环境为例，其他 Agent 请改为其技能目录。

Windows PowerShell：

```powershell
git clone https://github.com/Ibook000/product-showcase-film.git "$env:USERPROFILE\.codex\skills\product-showcase-film"
```

macOS / Linux：

```bash
git clone https://github.com/Ibook000/product-showcase-film.git "$HOME/.codex/skills/product-showcase-film"
```

## 脚本与示例

Python 3.10+、FFmpeg/FFprobe；图形模板使用 Pillow 和 numpy。只有原生三维渲染需要 Blender 4.2+。

```bash
python -m pip install -r scripts/requirements.txt
python scripts/showcase.py init work/project.json --demo
python scripts/showcase.py check work/project.json
python scripts/showcase.py plan work/project.json
python scripts/showcase.py preview work/project.json --preview-beats 0,2,4
python scripts/showcase.py render work/project.json
```

工具不在 PATH 时，可在配置中指定，或使用 `--blender`、`--ffmpeg`、`--ffprobe`。中文内容应指定或确认可用字体。

- [真实产品配置模板](assets/project-template.json)：替换真实素材与文案后使用。
- [原始几何示例](assets/demo-project.json)：独立部件与三维运镜，不含真实产品资产。
- [纯功能动效示例](assets/functional-project.json)：不需要 Blender。
- [配置与命令说明](references/project-format.md)
- [运镜与衔接方法](references/storyboard-motion.md)
- [跨环境与验证边界](references/portability-qa.md)

已在 Windows / Python 3.13 环境验证：三维拆装与相机变化、中文功能动效、照片素材流程、24 FPS / 128 BPM 拍点量化、字幕与配乐修改后的原生帧缓存复用，以及解压到新位置后独立执行。未将这些结果扩大为其他系统、任意产品效果或生成式视频服务已经验证。

## 相关技能

- [jlc-easyeda-design](https://github.com/Ibook000/jlc-easyeda-design)：嘉立创EDA原理图、电气审核与 PCB 设计流程。
- [product-enclosure-design](https://github.com/Ibook000/product-enclosure-design)：产品外壳建模、装配与开孔、STL 导出检查。

这两个技能不是本仓库的运行依赖。
