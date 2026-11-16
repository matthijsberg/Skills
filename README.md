# 🧠 Hermes Agent Skills Repository

A curated monorepo of production-grade, highly tested skills, extensions, and autonomous tools for **[Hermes Agent](https://hermes-agent.nousresearch.com)** and AI agent ecosystems.

---

## 📦 Skills Index

| Skill | Category | Version | Status | Description |
|---|---|---|---|---|
| **[`zeitgeist`](skills/zeitgeist/)** | `time` / `grounding` | `v1.2.1` | 🟢 Production | Dynamic temporal awareness, Stratum-1 atomic clock sync, deterministic NL/EN normalizer, 4-tier horizon matrix, holiday calendar & solar event calculator. |
| **[`homeassistant-addon-development`](skills/homeassistant-addon-development/)** | `devops` / `homeassistant` | `v2.0.0` | 🟢 Production | Build, upgrade, configure, and debug Home Assistant Add-ons (HA Apps), Supervisor API/SSH lifecycle, Ingress, S6-overlay, and security/CI gates. |

---

## 🚀 How to Install Skills in Hermes Agent

To install any skill from this repository into your active Hermes profile:

```bash
# Clone or copy the skill folder into your Hermes skills directory
git clone https://github.com/matthijsberg/Skills.git /tmp/skills
cp -r /tmp/skills/skills/zeitgeist ~/.hermes/skills/time/
```

Then run the automated setup script inside the skill directory:

```bash
bash ~/.hermes/skills/time/zeitgeist/scripts/setup.sh
```

---

## 🏛️ Skill Quality Standards

Every skill in this repository is built under strict **Test-Driven Development (TDD)** and operational standards:

1. **Deterministic Execution:** No hidden clock dependencies (`ClockPort` pattern).
2. **Comprehensive Test Suites:** Unit tests, boundary conditions, edge cases, and end-to-end scenarios tested via `pytest`.
3. **One-Click Setup & Demo (`scripts/setup.sh` & `scripts/demo.sh`):** Instant verification out-of-the-box.
4. **Zero-Hallucination Guardrails:** Clear output labeling (`[forecast]`, `[trend]`, `[climatology]`) to prevent LLM fabrications.
5. **No-Magic Architecture:** Readable, maintainable, modular Python code with type annotations.

---

## 📄 License

All skills in this repository are licensed under the [MIT License](LICENSE).
