# PLAN-031a GitHub 治理

## 目标

把 [Charlie780405/Qyunslation](https://github.com/Charlie780405/Qyunslation) 收成内部仓：Private、About 写明派生、关掉未用 Wiki/Projects、校正 remote、只删相对 main **0 ahead** 的过期 `feat/plan-*`。

## 操作

1. `gh repo edit Charlie780405/Qyunslation --visibility private --description '荃信内部文档翻译。派生自 xunbu/docutranslate（MPL-2.0）。'`
2. 关闭 Wiki / Projects（`gh repo edit --enable-wiki=false --enable-projects=false`）。
3. Remote（共享 `.git`，保留 `qyunslation` 以免其它 worktree 断跟踪）：
   - 现 `origin`（`xunbu/docutranslate`）改名为 `upstream`（只 fetch）
   - 若无 `origin` 指向本仓，则 `git remote add origin git@github.com:Charlie780405/Qyunslation.git`
   - 保留 `qyunslation` 与 `mirror`
4. 列出 `qyunslation` 远程分支相对 `main` 的 ahead/behind；**仅删除 0 ahead** 的过期 `feat/plan-*` / `feat/PLAN-*`。保留任何 ahead 分支（含 `codex/recovery-030e-030f-*`、`feat/PLAN-030*`、当前 031 分支）。

## 不做

- 不改写历史、不加 Collaborator
- 不删 ahead 分支

## 验收

- 仓库 `private`，description 含「派生」
- `git remote get-url origin` 指向 `Charlie780405/Qyunslation`
- `git remote get-url upstream` 指向 `xunbu/docutranslate`
