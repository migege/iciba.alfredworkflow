# 爱词霸 Alfred Workflow

```raw
@author  lzw.whu@gmail.com
@version 20260719:11
```

## 安装

[下载](https://github.com/migege/iciba.alfredworkflow/blob/master/bundle/iciba.alfredworkflow)

## 使用

```
ci <word>
```

![iciba.alfredworkflow](https://raw.githubusercontent.com/migege/iciba.alfredworkflow/master/screenshots/iciba.alfredworkflow.png)

```
ci > <word>
```

![iciba.alfredworkflow](https://raw.githubusercontent.com/migege/iciba.alfredworkflow/master/screenshots/iciba.alfredworkflow.2.png)

## 更新历史

|版本|更新内容|
|----|--------|
|20260719:11|修复 URL 编码/超时/异常处理等 Bug,清理 Python 2 残留代码,移除入库的 `.pyc`,`path_to_python3` 留空由用户配置,重新导出干净的 bundle|
|20220501:10|添加``$path_to_python3````变量，支持python3|
|20191227:01|添加```$path_to_python2```变量|
|20160908:03|支持中文|
|20160908:02|第一次输入获取suggest，回车后查词|
|20160907:01|初始版本|
