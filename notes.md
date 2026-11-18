# Kawaiicon 2026 — Talk Notes

Working notes for the deck. Each talk has a **Public summary** (taken from the official abstract and attendee
write-ups — see `sources.md`) and blank sections for your own notes. The slides are built from this file.

**Priority** controls slide count: `headline` = two slides, `standard` = one slide, `lightning` = shared lightning-round slide.

## Presentation

- **Audience:** Security team
- **Length:** 30–45 minutes
- **Presenter:**
- **Date presented:**

## Overall impressions

-

## Recurring themes (candidates — confirm, edit or replace)

1. **Signal vs noise** — vanity CVEs (Gutmann), broken CVE data (Lowe), red teams re-proving well-known paths (notnotcharlie & pruby). Spend effort where the real risk is.
2. **Attackers want sessions and secrets, not passwords** — infostealers stealing session cookies (Will & Jacob), API keys leaking from vibe-coded sites ("Alex").
3. **AI is accelerating both building and breaking** — agent-built products (Ayrey & Nolan), LLM-driven reverse engineering (John), LLM-assisted key hunting ("Alex").
4. **Sovereignty and supply chain** — self-hosted cloud (Shlee), 52-week chip lead times (Litchfield), privacy-preserving digital ID (von Dadelszen).
5. **People are the system** — diverse perspectives (Izzi), blameless incident response (D.Roc & Smiling Dragon), burnout (The Wizard), storytelling in red team reports.

## Actions for us (candidates)

- [ ] Deploy AWS / M365 canary tokens on developer machines; alert on use and on impossible travel
- [ ] Secret scanning on repos *and* deployed sites (e.g. trufflehog; check for exposed `.env` files)
- [ ] Turn on Kubernetes built-in security profiles before buying more tooling
- [ ] Triage CVEs by exploitability in our environment, not raw severity score
- [ ] Incident playbook: decision log, single comms owner, escalate early
- [ ] Inventory consumer/SOHO routers in use (incl. remote workers); retire EOL kit
- [ ] Start a post-quantum TLS readiness check (ML-KEM hybrid key exchange)
- [ ] Factor hardware lead times into device refresh planning

---

## 1. Vulnerability research & exploitation

### Vulnerability Research: how to get started hacking anything — Jim Rush
**Day/time:** Fri 30 Oct, 11:45am · **Theme:** Vulnerability research · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- The starting points for finding bugs are the same whatever the target: read the docs and existing research, map the attack surface, then start poking
- Argues for building your own repeatable research methodology rather than relying on tools
- Case study: digging into "cursed" Windows internals to expose attack surface and find bugs

**My notes:**
-

**Key takeaway:**

**So what for us:**

### Breaking Bad Routers: 6 Vendors, 6 Shells, 0 Days — MrBruh
**Day/time:** Fri 30 Oct, 1:45pm · **Theme:** Vulnerability research · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Audited firmware from six consumer router vendors: 28 vulnerabilities, unauthenticated RCE against every vendor tested
- Examples: forged auth tokens (Asus, D-Link), broken firmware-upload auth check (Motorola), mesh protocol that runs commands for any peer (Linksys Velop)
- Disclosure was mostly poor: D-Link unfixed after 90+ days, Linksys closed it as "theoretical"; TP-Link was the only vendor to fix within 90 days
- Recommendation: OpenWrt, or Ubiquiti (the one vendor without a finding)
- Not streamed or recorded — your own notes are the only source

**My notes:**
-

**Key takeaway:**

**So what for us:**

### Troubleshooting to SYSTEM: Local Privilege Escalation in Windows Diagnostics — Ben Wilson
**Day/time:** Fri 30 Oct, 5:00pm · **Theme:** Vulnerability research · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Windows Diagnostics (troubleshooters) is a privileged automation framework that can run scripts and binaries as SYSTEM
- Found three new local privilege escalation bugs by tracing how user input in help apps becomes privileged diagnostic execution
- Method: review diagnostic packages for attacker-controlled inputs, privileged operations and signature checks, then test with custom clients as a standard user

**My notes:**
-

**Key takeaway:**

**So what for us:**

---

## 2. Red teaming

### Red Teaming is dead. Long live Red Teaming. — notnotcharlie & Tim Goddard (pruby)
**Day/time:** Sat 31 Oct, 9:15am · **Theme:** Red teaming · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- External engagements usually prove one well-known path; more value comes from working with engineers and blue teams across the whole environment
- Don't spend time on well-secured, well-understood components — look at how they combine (unit vs integration tests)
- Internal red team (GitLab) deliberately generates incidents to test response, up to APT emulation with defanged malware
- Reports go to the whole company once fixed; storytelling and actionable fixes matter more than "we got domain admin"

**My notes:**
-

**Key takeaway:**

**So what for us:**

### How Is Red Team Infra Formed — Adam 'feabell' Bell
**Day/time:** Sat 31 Oct, 11:45am · **Theme:** Red teaming · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Core needs: an HTTP endpoint talking to C2, operator access, jump hosts and build servers; outsource the painful bits like SMTP
- "The Internet can see you" (e.g. certificate transparency) — use per-engagement upstream redirectors, blend in with benign traffic, don't serve payloads to non-targets
- Assume mistakes and hostile blue teams: restrict your own infra too
- Avoid the "Flamingo Up" (all campaigns exposed at once): compartmentalise, no reuse between campaigns, tear down after, keep a kill switch

**My notes:**
-

**Key takeaway:**

**So what for us:**

---

## 3. Signal vs noise: cryptography & vulnerability data

### The Cost of Stunt Cryptography — Peter Gutmann
**Day/time:** Fri 30 Oct, 10:15am · **Theme:** Signal vs noise · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- History of theoretical crypto attacks (from 1996's first side-channel attack onward) that never give a practical compromise
- The noise costs real money: developer time on patches with no benefit, FIPS recertification, sometimes *less* secure code paths
- Became a talk about the cost of vanity CVEs; suggests a "vanity" CVE severity

**My notes:**
-

**Key takeaway:**

**So what for us:**

### Much Ado About "n/a": The Tragedy of CVE5 Data Quality — Jess Lowe
**Day/time:** Fri 30 Oct, 2:30pm · **Theme:** Signal vs noise · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Live-coded a CVE5 parser against real records and watched it break: `"version": "Before Novemeber 13th"`, `"product": "n/a"`
- People who consume CVE data aren't represented; incentives push towards more CVEs and higher severity, not quality
- Speaker works on Google's OSV.dev; discussed alternatives and what can be done

**My notes:**
-

**Key takeaway:**

**So what for us:**

### ML-KEM in TLS — Ostap Cherkashin
**Day/time:** Sat 31 Oct, 3:45pm · **Theme:** Signal vs noise · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Quantum risk isn't all-or-nothing: weigh asset value, attack cost, environment complexity and implementation cost
- Explained ML-KEM (FIPS 203), the newly standardised post-quantum key exchange, and what its security rests on
- How ML-KEM integrates into TLS (RFC 9954), with practical web server configuration guidance
- Slides are published — see `sources.md`

**My notes:**
-

**Key takeaway:**

**So what for us:**

---

## 4. Identity, secrets & deception

### The cookie is a lie: Handing Canarytoken sessions to infostealers — Will & Jacob
**Day/time:** Fri 30 Oct, 11:15am · **Theme:** Identity & secrets · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Infostealers bypass MFA by stealing session tokens from browsers, along with credentials, cookies, messages and more
- Built fake companies seeded with canary tokens: infostealers triggered within 24 hours to 5 days, thousands of hits per company per week, data resold quickly
- AWS keys and Entra's long-lived `ESTSAUTHPERSISTENT` cookie make great canaries; using them logs a sign-in event
- Recommendation: AWS canary tokens on developer machines plus impossible-travel rules, and be ready to respond

**My notes:**
-

**Key takeaway:**

**So what for us:**

### Inside NZ's Digital Identity Stack (And How Do You Even Test This Thing?) — Nick von Dadelszen
**Day/time:** Fri 30 Oct, 4:30pm · **Theme:** Identity & secrets · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Problem: businesses take full copies of licences and passports when they only need one fact (e.g. age)
- Issuer / holder / verifier model: credential stored in the phone's secure hardware; holder shares only the requested subset; verifier must never report back to the issuer (enshrined in law)
- No new central database; first credentials are already being issued
- Open problems: old or rooted devices without secure elements; testing new protocols end-to-end (custom harness, ~2 years of work)

**My notes:**
-

**Key takeaway:**

**So what for us:**

### Finding vibe leaked API keys every day — "Alex"
**Day/time:** Sat 31 Oct, 2:30pm · **Theme:** Identity & secrets · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Pipeline: new domains from certificate transparency, then spider with httpx, then trufflehog to find and validate live keys
- Roughly 8–10 new valid keys per day, ~200 active at once (OpenAI, Stripe, Telegram, Hugging Face…) — a very conservative estimate
- Usually in exposed `.env` files or inline in `index.html`; revocation often takes weeks
- Vibe coders aren't stupid — help them rather than mock them

**My notes:**
-

**Key takeaway:**

**So what for us:**

---

## 5. Infrastructure, cloud & supply chain

### DIY Sovereign Cloud or: How I Learned to Stop Using Hyperscalers — Shlee
**Day/time:** Sat 31 Oct, 10:00am · **Theme:** Infrastructure · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- A "Coop Cloud" on second-hand enterprise hardware and open-source hypervisors, hosting hundreds of community services
- Cost comparison given: ~A$750/month for a half rack and 40 TB traffic vs ~A$7,500/month for a Linode equivalent
- Be realistic: you can't replace all of AWS, but a basic VM host is achievable
- Also covered ideology, data sovereignty, community building and risks

**My notes:**
-

**Key takeaway:**

**So what for us:**

### Building Leviathans — Robbie Litchfield
**Day/time:** Sat 31 Oct, 11:15am · **Theme:** Supply chain · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- The chip supply chain as five "contracts": extraction, refinement, design, fabrication, shipping
- Chip design relies on licensed IP blocks — "if you've ever used npm you understand how chip design works"; supply-chain attacks are coming for processors
- White, grey, black and restricted markets for components; lead times now up to 52 weeks for moderate volumes
- Suggestions: be flexible on BYOD, upgrade rather than replace, extend fleet life (e.g. Linux)

**My notes:**
-

**Key takeaway:**

**So what for us:**

### Kubernetes, it's no longer cool, but let's secure it anyway — Bea Hughes
**Day/time:** Sat 31 Oct, 12:15pm · **Theme:** Infrastructure · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Getting from zero to *some* security without breaking things or making developers do lots of work
- Enable the built-in security profiles to cut attack surface, rather than buying tools
- Root in a container matters less than the database and cloud credentials it can reach — secure the apps
- Block crypto-mining domains; "shoot the hostage": replace the container shell with one that kills the pod
- Slides are published — see `sources.md`

**My notes:**
-

**Key takeaway:**

**So what for us:**

---

## 6. AI & how we work

### Want me to take it from here? Changing how we work, live, and relate to the criminal justice system — Dylan Ayrey & Michael Nolan
**Day/time:** Fri 30 Oct, 9:15am (opening talk) · **Theme:** AI · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Started from a team shipping a customer-facing API portal over a weekend, mostly agent-written, and how that changed planning, review and "who is fast"
- Presented as a dramatised "spooky tale": AI doomers, stand-ups, vibe coding, and a model let loose on a company's internal systems
- How workplace dynamics and technology choices intersect with legal consequences

**My notes:**
-

**Key takeaway:**

**So what for us:**

### plz don't hallucinate my childhood — John
**Day/time:** Sat 31 Oct, 1:45pm · **Theme:** AI · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Old games decay without source code or maintenance; manual engine rewrites take years
- Tried using LLMs for reverse engineering to port a 2D RPG to the web
- What worked: agentic orchestration, semantic behaviour graphs, feedback loops — playable port in a few weekends plus a month of background LLM work

**My notes:**
-

**Key takeaway:**

**So what for us:**

---

## 7. People, culture & resilience

### Panel: Getting into the cybers — The Whimsical Panel MC
**Day/time:** Fri 30 Oct, 10:30am & Sat 31 Oct, 12:45pm · **Theme:** People · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Moderated Q&A for people wanting to get into cybersecurity, covering how the industry splits (red, blue, GRC)
- Panellists ranged from early-career people to long-time industry veterans

**My notes:**
-

**Key takeaway:**

**So what for us:**

### A SecOps manager, an epidemiologist and a bacterium walk into a bar — Izzi
**Day/time:** Fri 30 Oct, 12:15pm · **Theme:** People · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- John Snow and the 1854 Broad Street cholera outbreak: experts blamed "miasma"; Snow's different background led him to different questions and a map that found the pump
- Question quick consensus: is this the real cause or just the obvious one? Who isn't in the room?
- Test the theory against all the cases, including inconvenient exceptions
- Make it stick: understandable at a glance, works when you're not in the room. "Slow is smooth, smooth is fast"

**My notes:**
-

**Key takeaway:**

**So what for us:**

### How to have a successful failure — D.Roc & Smiling Dragon
**Day/time:** Fri 30 Oct, 3:00pm · **Theme:** People · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Incident response lessons drawn from the 1988 Piper Alpha oil platform disaster
- Keep a decision log (for the RCA and for your own peace of mind); make decisions that keep options open
- Clear command structure with one known comms owner; call in help early (e.g. regulators)
- Look after the team: blameless culture; only mention individuals to praise them

**My notes:**
-

**Key takeaway:**

**So what for us:**

### Heed The Wizard's Warnings — Burnout mitigation strategies & observability advice for Yourself-as-a-Service — The Wizard
**Day/time:** Sat 31 Oct, 2:00pm · **Theme:** People · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Burnout is complex and multi-causal, and easier to prevent than to fix; covered useful models and practical "dashboard metrics" for yourself
- Warning signs: a shrinking world, stepping back from the things that fill your cup
- Build physical, mental and social practices, plus a hobby where you make something physical; challenge learned assumptions about yourself

**My notes:**
-

**Key takeaway:**

**So what for us:**

---

## 8. Hacker spirit

### My Accidental Neopets Crime Ring — Zelle Marcovicci
**Day/time:** Fri 30 Oct, 4:15pm · **Theme:** Hacker spirit · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- Rare and legacy Neopets names drive a black market and trading groups
- Neopets security was poor (plain-text personal data); forced password resets plus lapsed email addresses, or social engineering support, made account takeover easy
- Every step was reasonable in isolation; the same techniques can be used to help people recover childhood accounts

**My notes:**
-

**Key takeaway:**

**So what for us:**

### What's in ya tubs — richö butts
**Day/time:** Sat 31 Oct, 4:15pm · **Theme:** Hacker spirit · **Priority:** [ ] headline [ ] standard [ ] lightning

**Public summary:**
- A tour of richö's project tubs: home-made carbon fibre parts, an espresso machine running Rust on a microcontroller, and vulnerabilities in a home solar system
- No write-ups found — your notes are the main source

**My notes:**
-

**Key takeaway:**

**So what for us:**
