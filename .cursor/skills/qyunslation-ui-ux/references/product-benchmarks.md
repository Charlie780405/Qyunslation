# 中英翻译产品 UI/UX 深度基准

## 研究范围与结论

本基准聚焦中英文本、文档、图片和专业审校，不比较语言数量或单纯模型分数。资料优先采用产品官方帮助、官方仓库和论文。检索与核验日期：2026-09-13。

结论：Qyunslation 不应复制某一个竞品，而应组合三类成熟模式：

1. DeepL/Google 的低门槛入口与渐进式设置；
2. 沉浸式翻译的原译文并读与对象直接修复；
3. Smartcat/Weblate/Crowdin 的术语、翻译记忆、QA、历史和状态治理。

最终差异化不是“再做一个左右翻译框”，而是把医药文档的页面保真、Figure/Table/脚注、剂量数字、参考文献保护和可审计审校统一在一个工作台。

## 对比矩阵

| 产品/项目 | 值得学习 | 明显短板 | Qyunslation 取舍 |
| --- | --- | --- | --- |
| DeepL | 双栏输入简洁；文件拖放；术语表、风格规则、翻译记忆和审阅按需出现；文档格式保留[^1][^2] | 文件翻译更像上传—等待—下载；替换译法等直接操作不完整覆盖文件场景[^3]；缺少页/表/图对象审计 | 学入口简洁、选择替换和渐进披露；补上对象 Manifest、页内审校和医药 QA |
| Google Translate | 文本/图片/文档/网站用模态标签分流；主动作清楚；图片可切原文、并排、复制和下载[^4][^5] | 专业术语、审校、历史和 QA 很弱；扫描 PDF 文本可能检测但不一定翻译，文档入口移动端受限[^4] | 学模态入口和图片原文开关；不采用“翻完即结束”的消费级流程 |
| 百度翻译 | 中国用户熟悉；文档保排版、双语对照、生物医药领域和图片场景回写均有产品表达[^6][^7] | 能力入口多，门户感较强；质量依据、对象状态和失败边界不够透明 | 学中文术语与多模态引导；所有识别与降级必须在预扫描和 QA 中显式呈现 |
| 沉浸式翻译 | 段落级双语并读、悬停交互、PDF 原译切换；部分 PDF 文本框可移动和编辑[^8][^9] | 多栏重排常转单栏，牺牲原位布局；表格/公式和文本重叠仍需人工修复[^9]；当前 GitHub 仓库主要发布版本和收集问题，不是可复用源码[^10] | 学双语阅读、原文开关和直接修复；坚持 Manifest 锚点与保真画布，不把重排当默认 |
| Smartcat | 源/目标分段编辑、CAT 建议、术语/TM、QA、评论、历史形成闭环[^11][^12] | 专业能力密度高，新用户学习成本大；页面视觉上下文弱 | 专业模式借鉴 CAT 检查器；快速模式不暴露分段网格和项目管理复杂度 |
| Crowdin | 从来源、上下文、预翻译、QA 到交付的管线清楚；术语有状态，配置可复用[^13][^14] | 面向软件本地化和团队项目，文档页/图表保真不是中心；企业导航过重 | 学状态、来源、术语资产和质量门禁；不复制项目/字符串中心的信息架构 |
| Weblate | 开源；编辑器整合检查、TM、术语、截图、历史、快捷键和 Zen 模式；术语支持首选/禁译等类型[^15][^16] | 主要服务软件字符串，本地化管理概念较多 | 学键盘、状态化术语、历史和专注模式；换成文档对象而非字符串单元 |
| MateCat | 开源 Web CAT，TM/MT 与项目协作成熟[^17] | 技术栈与界面负担较重，页面保真和图片/表格不是第一目标 | 借鉴确认分段与语言资产闭环，不以传统 CAT 网格替代文档画布 |
| PDFMathTranslate Web / BabelDOC | Vue 文档上传路径短；科学 PDF 单/双语产物明确；开源便于研究[^18][^19] | 入口简洁但审校、术语、QA、对象修复和团队流程有限 | 保留简单入口；把翻译后的页面变成可工作的对象化审校界面 |
| LibreTranslate / Argos Translate | 开源、自托管、离线和 API 边界简单[^20][^21] | 主要是文本/API 能力，不解决复杂文档 UI/UX | 可作为引擎/降级参照，不作为界面蓝本 |
| TranSmart | 论文展示交互式机器翻译可结合词/句补全和翻译记忆，说明“人在环”能提升专业工作流[^22] | 研究系统模式不等同于现代成品界面，不能直接照搬 | 后续专业编辑器可加入术语补全和整句建议，但必须可撤销、可追溯 |

## 可直接转化的设计原则

### 1. 首屏只做一个决定

上传文件后，用户只需确认中英方向、文档类型和是否立即翻译。模型、OCR、并发、缓存等工程参数放入自动策略或高级设置。DeepL 和 Google 的共同优势不是功能少，而是默认路径短。

### 2. 翻译结果不是终点，而是可审校资产

消费级产品到“下载”为止，专业产品以“确认”为核心。Qyunslation 应让用户能从 QA 问题跳到页面对象，查看原文、候选译文、术语命中、格式状态和修改历史，再确认该对象。

### 3. 页面上下文与语言工具必须同时存在

传统 CAT 擅长分段但弱化版面；PDF 阅读器保留版面却缺乏术语和 QA。中央双画布 + 右侧对象检查器能兼顾二者，且更适合医药表格、图注、剂量和参考文献。

### 4. 术语是工作流，不是静态 CSV

术语至少需要 `preferred/protected/do_not_translate/forbidden/variant` 状态、来源、适用方向、领域和版本。界面应展示命中与冲突，允许从选中文本添加，经审核后再进入项目或组织词库。

### 5. 失败要比“看起来成功”更显眼

扫描截断、表格未识别、图片 OCR 失败、字体溢出、参考文献误译都必须产生结构化问题。对医药资料而言，一个安静的漏译比显式阻断更危险。

## 不应照搬

- 不照搬 DeepL/Google 的“左右文本框就是全部产品”。
- 不照搬 CAT 工具默认全屏分段表格，新用户会失去页面上下文。
- 不照搬沉浸式翻译的默认单栏重排作为原位保真方案。
- 不照搬本地化平台的项目、字符串、分支和资源树术语。
- 不照搬竞品品牌色、图标、文案、页面截图或闭源实现。

## 来源

[^1]: DeepL, [About file translation](https://support.deepl.com/hc/en-us/articles/360020582499-About-file-translation).
[^2]: DeepL, [Edit your file translation](https://support.deepl.com/hc/en-us/articles/21315109374748-Edit-your-file-translation).
[^3]: DeepL, [Select alternatives](https://support.deepl.com/hc/en-us/articles/4407359201938-Select-alternatives); [About the glossary](https://support.deepl.com/hc/en-us/articles/360021634540-About-the-glossary).
[^4]: Google Translate Help, [Translate documents & websites](https://support.google.com/translate/answer/2534559?co=GENIE.Platform%3DDesktop&hl=en).
[^5]: Google Translate Help, [Translate images](https://support.google.com/translate/answer/6142483?co=GENIE.Platform%3DDesktop&hl=en-gb).
[^6]: 百度翻译, [产品首页](https://fanyi.baidu.com/home).
[^7]: 百度翻译开放平台, [文档与图片翻译](https://api.fanyi.baidu.com/); [图片翻译 V2](https://api.fanyi.baidu.com/product/23).
[^8]: Immersive Translate, [Documentation](https://immersivetranslate.com/docs/).
[^9]: Immersive Translate, [PDF translation](https://immersivetranslate.com/docs/features/pdf/); [PDF helper](https://immersivetranslate.com/en/docs/pdf-helper/).
[^10]: Immersive Translate, [GitHub repository](https://github.com/immersive-translate/immersive-translate).
[^11]: Smartcat, [Editor functionalities overview](https://help.smartcat.com/editor-functionalities-overview/).
[^12]: Smartcat, [Linguistic resources in the editor](https://help.smartcat.com/managing-linguistic-resources-in-the-editor/); [Quality assurance](https://help.smartcat.com/quality-assurance/).
[^13]: Crowdin, [Localization workflow](https://crowdin.com/).
[^14]: Crowdin, [Translation Portal](https://store.crowdin.com/translation-portal).
[^15]: Weblate, [Translating documentation](https://github.com/WeblateOrg/weblate/blob/main/docs/user/translating.rst).
[^16]: Weblate, [Glossary documentation](https://github.com/WeblateOrg/weblate/blob/main/docs/user/glossary.rst).
[^17]: MateCat, [Official repository](https://github.com/matecat/MateCat).
[^18]: PDFMathTranslate, [Web UI repository](https://github.com/PDFMathTranslate/PDFMathTranslate-Web).
[^19]: PDFMathTranslate, [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next); [BabelDOC](https://github.com/funstory-ai/BabelDOC).
[^20]: LibreTranslate, [Official repository](https://github.com/LibreTranslate/LibreTranslate).
[^21]: Argos Translate, [Official repository](https://github.com/argosopentech/argos-translate).
[^22]: Tencent AI Lab, [TranSmart: A Practical Interactive Machine Translation System](https://arxiv.org/abs/2105.13072).
