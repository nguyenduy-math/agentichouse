# Branch Strategy

[← Back to Standards](../README.md)

---

```
main          ← production-ready, protected
└── develop   ← integration branch
    ├── feat/TICKET-short-description
    ├── fix/TICKET-short-description
    └── chore/short-description
```

- `main` and `develop` are protected; direct push is blocked.
- Feature branches deleted after merge.
