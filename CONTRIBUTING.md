# 贡献指南

感谢你对 Plato 的关注！

## 如何贡献

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/my-feature`
3. 提交改动：`git commit -m "feat: add my feature"`
4. 推送到分支：`git push origin feature/my-feature`
5. 提交 Pull Request

## 开发环境

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd rust_engine && maturin develop --release && cd ..
cd frontend && npm install && cd ..
```

## Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档
- `refactor:` 重构
- `test:` 测试
- `chore:` 构建/工具

## 提交前检查

```bash
python manage.py check          # Django 检查
cd rust_engine && cargo test    # Rust 测试
```
