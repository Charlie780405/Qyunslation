# PLAN-072c：分片上传与断点续传

> 状态：**实施中**
> 父计划：[README](./README.md)

## 目标

大文件上传中断后可从已接收偏移继续，sha256 秒传前置到会话创建。

## 任务

1. `upload_session` 表 + 三端点：POST 创建、PATCH 追加、POST 完成转 preflight。
2. GET 会话状态（已接收字节）。
3. 前端分片上传；`localStorage` 按 tenant+sub 记 uploadId。

## 验收

- 中断后续传 sha256 与整传一致。
- 命中已有 sha256 直接返回 preflight。
