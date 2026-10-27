# 爱词霸 Alfred Workflow

```raw
@author  lzw.whu@gmail.com
@version 20261027:15
```

## 安装

[下载](https://github.com/migege/iciba.alfredworkflow/blob/master/bundle/iciba.alfredworkflow)

需要 Python 3，无需安装第三方包。在 Alfred Workflow 的变量中，将 `path_to_python3` 设置为 Python 3 可执行文件的完整路径；留空时使用 Alfred 的 `PATH` 中的 `python3`。

## 使用

```
ci <word>
```

![iciba.alfredworkflow](https://raw.githubusercontent.com/migege/iciba.alfredworkflow/master/screenshots/iciba.alfredworkflow.png)

```
ci > <word>
```

![iciba.alfredworkflow](https://raw.githubusercontent.com/migege/iciba.alfredworkflow/master/screenshots/iciba.alfredworkflow.2.png)

输入单词时优先显示建议；建议服务不可用或没有匹配时，自动继续查词与翻译。包含空格的短语或句子直接查词，无需输入 `>` 或先按回车。查词和本地翻译都失败时，回车打开词霸网页。

## Apple 本地翻译回退

查词会依次尝试词典释义、词霸普通机器翻译、Apple 本地翻译。只有前两项均无有效结果，或查词服务异常时，才调用 Apple；空白释义和原文照抄不算有效结果。有效建议不触发本地翻译；普通输入也能在建议失败后自动进入翻译。

若自动识别把单个拉丁字母单词判断为未安装或不支持的语言，会再按英语尝试一次；手动指定 `translation_source` 时不会覆盖。Apple 返回原文或空译文时显示“未找到翻译”，不会提示服务不可用。语言包缺失和语言组合不受支持会分别提示，并显示本次识别的语言组合。

输入采用短暂停顿后处理、首个字符立即处理的方式。新输入会终止旧查询，同时清理旧查询启动的本地翻译进程；建议请求最多等待 0.5 秒，普通查词请求最多等待 2 秒，避免失效接口长时间占住结果。

本地翻译需要 macOS 26 或更新版本，支持 Apple 芯片与 Intel Mac。首次使用前，在 **系统设置 → 通用 → 语言与地区 → 翻译语言** 中下载源语言和目标语言，默认是英语和中文。缺少语言包时会显示提示，仍可打开词霸网页。无需 API Key，翻译由设备本地处理；macOS 26.4+ 优先使用 Apple 的 highFidelity 策略，不可用时由系统回退到传统翻译模型。

Workflow 变量：

|变量|默认值|说明|
|----|------|----|
|`apple_translation`|`1`|设为 `0` 关闭本地翻译回退|
|`translation_source`|留空|自动识别；可指定 `en`、`zh-Hans` 等语言代码|
|`translation_target`|留空|中文译为英语，其他语言译为简体中文；可指定语言代码|

[Apple TranslationSession 文档](https://developer.apple.com/documentation/Translation/TranslationSession) · [下载离线翻译语言](https://support.apple.com/en-me/guide/mac-help/mchldd8b3c15/mac)

## 开发与验证

```sh
python3 scripts/build_workflow.py
python3 -m unittest discover -s tests -v
```

构建脚本只打包运行所需 Python 源码、图标、配置和预编译的通用翻译组件，不包含字节码或本机环境。修改 `native/AppleTranslate.swift` 后，先在装有 Xcode 26.4+ 的 Mac 上运行 `python3 scripts/build_native.py`，再打包。原生集成测试会检查语言状态；未安装语言包时会跳过真实翻译测试。

## 更新历史

|版本|更新内容|
|----|--------|
|20261027:15|区分未找到译文、缺少语言包及翻译错误；单词被误判为其他不可用语言时按英语重试|
|20261027:14|修复普通输入无法自动进入翻译、建议接口超时导致输入滞后；短语跳过建议，缩短网络等待，并在取消查询时清理翻译子进程|
|20261027:13|词典及普通翻译均无有效结果时回退到 Apple 本地翻译，支持语言配置及缺失语言包提示|
|20261027:12|移除 requests 依赖，建议服务异常时可直接查词，使用 HTTPS 与安全的参数传递，修复查询模式识别及网页 URL 编码，添加回归测试和打包脚本|
|20260719:11|修复 URL 编码/超时/异常处理等 Bug,清理 Python 2 残留代码,移除入库的 `.pyc`,`path_to_python3` 留空由用户配置,重新导出干净的 bundle|
|20220501:10|添加``$path_to_python3````变量，支持python3|
|20191227:01|添加```$path_to_python2```变量|
|20160908:03|支持中文|
|20160908:02|第一次输入获取suggest，回车后查词|
|20160907:01|初始版本|
