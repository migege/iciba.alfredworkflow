# 爱词霸 Alfred Workflow

```raw
@author  lzw.whu@gmail.com
@version 20261027:12
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

建议服务不可用或没有匹配时，回车可直接查词；查词失败时，回车打开词霸网页。

## 开发与验证

```sh
python3 scripts/build_workflow.py
python3 -m unittest discover -s tests -v
```

构建脚本只打包运行所需源码、图标和配置，不包含字节码或本机环境。

## 更新历史

|版本|更新内容|
|----|--------|
|20261027:12|移除 requests 依赖，建议服务异常时可直接查词，使用 HTTPS 与安全的参数传递，修复查询模式识别及网页 URL 编码，添加回归测试和打包脚本|
|20260719:11|修复 URL 编码/超时/异常处理等 Bug,清理 Python 2 残留代码,移除入库的 `.pyc`,`path_to_python3` 留空由用户配置,重新导出干净的 bundle|
|20220501:10|添加``$path_to_python3````变量，支持python3|
|20191227:01|添加```$path_to_python2```变量|
|20160908:03|支持中文|
|20160908:02|第一次输入获取suggest，回车后查词|
|20160907:01|初始版本|
