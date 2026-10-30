import html as html_lib
import os
import re
from agents.llm import LLMClient, make_client
import streamlit as st
from dotenv import load_dotenv

from agents.parser import run_parser
from agents.specialists import run_specialists
from agents.synthesizer import run_synthesizer
from agents.guardrails import check_guardrail, extract_report_text, scan_jd_for_violations
from models.context import JDQIContext
from agents.jd_builder_gather import gather_turn, greeting
from agents.jd_builder_draft import draft_jd
from agents.jd_docx import build_docx, extract_jd_text

load_dotenv(override=True)

INDUSTRIES = ["High-tech Manufacturing", "IT/SaaS/AI", "GCC", "Other"]

DIM_LABELS = {
    "completeness":      "Completeness",
    "skill_specificity": "Skill Specificity",
    "cognitive_load":    "Cognitive Load",
    "inclusion_signals": "Inclusion Signals",
    "compensation":      "Compensation",
    "role_coherence":    "Role Coherence",
}


_BRAND_PRESETS = {
    "Corporate Navy": "#1D3557",
    "JDQI Red":       "#C8102E",
    "Charcoal":       "#2D2D2D",
}


def _score_badge(score: int) -> tuple[str, str]:
    """Return (label, delta_color) for a JDQI score."""
    if score >= 75:
        return "Excellent", "normal"
    if score >= 50:
        return "Fair", "off"
    return "Needs Work", "inverse"


def _get_client() -> LLMClient:
    try:
        return make_client()
    except KeyError as e:
        st.error(
            f"**{e.args[0]} not set.** Add AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT "
            "and AZURE_OPENAI_DEPLOYMENT to `.env` and restart."
        )
        st.stop()


def _build_highlighted_html(jd_text: str, phrases: list[str]) -> str:
    """Return the JD as an HTML block with each phrase wrapped in an amber <mark>."""
    safe = html_lib.escape(jd_text)

    sorted_phrases = sorted(phrases, key=len, reverse=True)
    deduped: list[str] = []
    for p in sorted_phrases:
        if not any(p.lower() in longer.lower() for longer in deduped):
            deduped.append(p)

    mark_open = (
        '<mark style="background:#FEF3C7;color:#92400E;'
        'padding:1px 4px;border-radius:3px;font-weight:600;">'
    )
    mark_close = "</mark>"

    for phrase in deduped:
        safe_phrase = html_lib.escape(phrase)
        pattern = re.compile(re.escape(safe_phrase), re.IGNORECASE)
        safe = pattern.sub(lambda m: f"{mark_open}{m.group(0)}{mark_close}", safe)

    return (
        '<div style="background:white;border:1px solid #e2e8f0;border-radius:6px;'
        "padding:14px;font-family:monospace;font-size:13px;line-height:1.7;"
        'white-space:pre-wrap;max-height:300px;overflow-y:auto;">'
        f"{safe}</div>"
    )


def _render_jd_with_highlights(jd_text: str, phrases: list[str]) -> None:
    """Render the JD panel with highlighted phrases below the guardrail error banner."""
    count = len(phrases)
    badge_color = "#ef4444" if count > 0 else "#64748b"
    badge_text = (
        f"{count} phrase{'s' if count != 1 else ''} flagged"
        if count > 0
        else "no specific phrases identified"
    )
    st.markdown(
        '<div style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-top:8px;">'
        '<div style="background:#1e293b;color:#f8fafc;padding:10px 14px;'
        'font-size:13px;font-weight:600;">'
        f'🔍 Issues found in your JD '
        f'<span style="background:{badge_color};color:white;font-size:11px;'
        f'padding:2px 8px;border-radius:10px;margin-left:6px;">{badge_text}</span>'
        "</div></div>",
        unsafe_allow_html=True,
    )
    if phrases:
        st.caption(
            "Highlighted phrases likely triggered the guardrail — revise them and re-analyse."
        )
        st.markdown(_build_highlighted_html(jd_text, phrases), unsafe_allow_html=True)
    else:
        st.caption(
            "Could not automatically pinpoint specific phrases. "
            "Review your JD for language that could be considered discriminatory or exclusionary."
        )


def run_pipeline(jd_text: str, industry: str, client: LLMClient) -> None:
    context: JDQIContext = {"jd_text": jd_text, "industry": industry}

    st.divider()
    st.subheader("Pipeline")

    # ── Content Safety Guardrail — INPUT gate ───────────────────────────────
    input_ph = st.empty()
    input_ph.info("🛡️ **Content Safety Guardrail (INPUT)**  Validating JD text...")
    gr_in = check_guardrail(jd_text, "INPUT")
    if not gr_in.passed:
        input_ph.error(
            f"🚫 **Content Safety Guardrail (INPUT) — Blocked.**  {gr_in.blocked_reason or 'content policy violation'}"
        )
        return
    input_ph.success("✅ **Content Safety Guardrail (INPUT)**  Passed")

    # ── Agent 1: JD Parser ───────────────────────────────────────────
    parser_ph = st.empty()
    parser_ph.info("⏳ **Agent 1 — JD Parser** (Sonnet)  Extracting structure...")
    try:
        context["parsed_jd"] = run_parser(jd_text, industry, client)
        parsed = context["parsed_jd"]
        parser_ph.success(
            f"✅ **Agent 1 — JD Parser**  "
            f"`{parsed['role_title']}` · {parsed['seniority_level']} · "
            f"{len(parsed['required_skills'])} required skills"
        )
    except Exception as e:
        parser_ph.error(f"❌ JD Parser failed — {e}")
        return

    # ── Agents 2–7: Specialist Analyzers (parallel) ──────────────────
    st.write("**Agents 2–7 — Specialist Analyzers** (Sonnet, parallel)")
    spec_cols = st.columns(3)
    spec_phs: dict[str, st.delta_generator.DeltaGenerator] = {}

    for i, (key, label) in enumerate(DIM_LABELS.items()):
        ph = spec_cols[i % 3].empty()
        ph.info(f"⏳ {label}")
        spec_phs[key] = ph

    def on_specialist_done(key: str, result: dict) -> None:
        spec_phs[key].success(f"✅ {DIM_LABELS[key]} — {result.get('score', '?')}/100")

    try:
        context["dimension_results"] = run_specialists(
            jd_text, context["parsed_jd"], client, on_specialist_done
        )
    except Exception as e:
        st.error(f"Specialist analysis failed — {e}")
        return

    # ── Agents 8 + 9: Synthesis Executor → Advisor ───────────────────
    synth_ph = st.empty()
    synth_ph.info("⏳ **Agent 8 — Synthesis Executor** (Sonnet)  Building brief...")

    advisor_ph = st.empty()
    advisor_ph.warning("🔶 **Agent 9 — Advisor** (Opus)  Waiting for tool call...")

    def on_advisor_called() -> None:
        synth_ph.info("⏳ **Agent 8 — Synthesis Executor**  Tool call dispatched → Advisor")
        advisor_ph.warning("🔶 **Agent 9 — Advisor** (Opus)  Consulting... (~30s)")

    try:
        context["advisor_report"] = run_synthesizer(context, client, on_advisor_called)
        score = context["advisor_report"]["jdqi_score"]
        synth_ph.success("✅ **Agent 8 — Synthesis Executor**  Complete")
        advisor_ph.success(f"✅ **Agent 9 — Advisor** (Opus)  JDQI Score: **{score}/100**")
    except Exception as e:
        advisor_ph.error(f"❌ Advisor failed — {e}")
        return

    # ── Content Safety Guardrail — OUTPUT gate ──────────────────────────────
    output_ph = st.empty()
    output_ph.info("🛡️ **Content Safety Guardrail (OUTPUT)**  Validating advisor report...")
    report_text = extract_report_text(context["advisor_report"])
    gr_out = check_guardrail(report_text, "OUTPUT")
    if not gr_out.passed:
        output_ph.error(
            f"🚫 **Content Safety Guardrail (OUTPUT) — Blocked.**  {gr_out.blocked_reason or 'content policy violation'}"
        )
        with st.spinner("Scanning JD for problematic phrases…"):
            phrases = scan_jd_for_violations(jd_text, gr_out.blocked_reason or "", client)
        _render_jd_with_highlights(jd_text, phrases)
        return
    output_ph.success("✅ **Content Safety Guardrail (OUTPUT)**  Passed")

    st.session_state.jdqi_context = context
    st.session_state.accepted = []


def display_report(context: JDQIContext) -> None:
    report = context["advisor_report"]
    score = report["jdqi_score"]
    label, delta_color = _score_badge(score)

    st.divider()
    st.subheader("JDQI Report")

    col1, col2 = st.columns([1, 3])
    col1.metric("JDQI Score", f"{score} / 100", delta=label, delta_color=delta_color)
    col2.progress(score / 100)

    # ── Dimension breakdown ──────────────────────────────────────────
    st.subheader("Dimension Breakdown")
    for item in report["dimension_breakdown"]:
        dim = item["dimension"]
        c1, c2, c3 = st.columns([2, 1, 5])
        c1.write(f"**{DIM_LABELS.get(dim, dim.replace('_', ' ').title())}**")
        c2.write(f"**{item['score']}**/100")
        c3.progress(item["score"] / 100)
        st.caption(f"\u00a0\u00a0{item['narrative']}")

    # ── Benchmark comparison ─────────────────────────────────────────
    with st.expander("Benchmark Comparison — Opus Analysis", expanded=False):
        st.write(report["benchmark_comparison"])

    # ── Suggested additions ──────────────────────────────────────────
    st.divider()
    st.subheader("Suggested Additions")
    st.caption("Accept suggestions to build your revised JD additions list.")

    for i, s in enumerate(report["suggested_additions"]):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 4, 3, 1])
            c1.write(f"**{s['section']}**")
            c2.write(s["suggestion"])
            c3.caption(s["impact"])
            if c4.button("Accept", key=f"accept_{i}"):
                entry = f"[{s['section']}] {s['suggestion']}"
                if entry not in st.session_state.accepted:
                    st.session_state.accepted.append(entry)
                    st.rerun()

    if st.session_state.get("accepted"):
        st.subheader("Revised JD Additions")
        st.code("\n\n".join(st.session_state.accepted), language=None)
        if st.button("Clear selections"):
            st.session_state.accepted = []
            st.rerun()


_MAX_DRAFT_RETRIES = 3


def _run_draft(client: LLMClient) -> None:
    """Run Phase 2: draft the JD with live progress and guardrail course-correction."""
    with st.chat_message("assistant"):
        ph = st.empty()
        feedback: str | None = None
        doc = None

        for attempt in range(1, _MAX_DRAFT_RETRIES + 1):
            if attempt == 1:
                ph.markdown(
                    "⏳ **Generating your JD…**\n\n"
                    "- ✍️  Step 1/3 — Drafting from your brief… _(~20s)_"
                )
            else:
                ph.markdown(
                    f"♻️ **Course-correcting (attempt {attempt}/{_MAX_DRAFT_RETRIES})…**\n\n"
                    f"- ✅  Previous draft blocked — rewriting to fix guardrail issues\n"
                    f"- ✍️  Redrafting with corrections applied…"
                )

            doc = draft_jd(st.session_state.jdqi_brief, client, guardrail_feedback=feedback)

            ph.markdown(
                f"⏳ **Generating your JD…** _(attempt {attempt})_\n\n"
                "- ✅  Draft complete\n"
                "- 🛡️  Running Content Safety Guardrail (OUTPUT)…"
            )
            gr_out = check_guardrail(extract_jd_text(doc), "OUTPUT")

            if gr_out.passed:
                break

            feedback = gr_out.blocked_reason
            if attempt == _MAX_DRAFT_RETRIES:
                ph.error(
                    f"🚫 Could not produce a guardrail-compliant JD after "
                    f"{_MAX_DRAFT_RETRIES} attempts.\n\n**Last block reason:** {feedback}"
                )
                return

            ph.markdown(
                f"♻️ **Guardrail blocked — course-correcting…**\n\n"
                f"_{feedback}_\n\n"
                f"Rewriting to fix these issues before attempt {attempt + 1}…"
            )

        ph.markdown(
            "⏳ **Generating your JD…**\n\n"
            "- ✅  Draft complete\n"
            "- ✅  Guardrail passed\n"
            "- 📄  Building your branded .docx…"
        )
        build_docx(doc, st.session_state.brand_color, st.session_state.logo_bytes)
        ph.success("✅ Your JD is ready! Scroll down to download.")

    st.session_state.jd_document = doc
    st.rerun()


def _build_jd_tab(client: LLMClient) -> None:
    """Render the Build JD chat tab."""

    # ── Brand settings ───────────────────────────────────────────────
    with st.expander("⚙️ Brand Settings", expanded=False):
        bcols = st.columns(len(_BRAND_PRESETS) + 1)
        for i, (name, hex_val) in enumerate(_BRAND_PRESETS.items()):
            if bcols[i].button(f"● {name}", key=f"preset_{name}"):
                st.session_state.brand_color = hex_val
                st.rerun()
        custom = bcols[-1].text_input(
            "Custom hex", value=st.session_state.brand_color, key="custom_color_input"
        )
        if custom != st.session_state.brand_color and custom.startswith("#") and len(custom) == 7:
            st.session_state.brand_color = custom

        logo_file = st.file_uploader("Company Logo (PNG/JPG, optional)", type=["png", "jpg", "jpeg"])
        if logo_file:
            st.session_state.logo_bytes = logo_file.read()

    st.caption(f"Brand color: `{st.session_state.brand_color}`")

    # ── Seed greeting on first load ──────────────────────────────────
    if not st.session_state.builder_messages:
        first = greeting()
        st.session_state.builder_messages.append({"role": "assistant", "content": first})

    # ── Chat display ─────────────────────────────────────────────────
    for msg in st.session_state.builder_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Download section (shown after successful generation) ─────────
    if st.session_state.jd_document is not None:
        st.divider()
        role = st.session_state.jd_document.get("role_title", "Job Description")
        st.success(f"📄 JD ready — **{role}**")
        docx_bytes = build_docx(
            st.session_state.jd_document,
            st.session_state.brand_color,
            st.session_state.logo_bytes,
        )
        col1, col2 = st.columns(2)
        col1.download_button(
            "⬇ Download .docx",
            data=docx_bytes,
            file_name=f"{role.replace(' ', '_')}_JD.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        if col2.button("🔄 Start over"):
            for key in ("builder_messages", "jdqi_brief", "jd_document", "logo_bytes"):
                st.session_state[key] = [] if key == "builder_messages" else None
            st.session_state.ready_to_generate = False
            st.rerun()
        return  # Don't show chat input once JD is done

    # ── Generate button (shown when gather agent signals ready) ──────
    if st.session_state.ready_to_generate and st.session_state.jdqi_brief:
        if st.button("✅ Generate JD now", type="primary"):
            _run_draft(client)
            return

    # ── Chat input ───────────────────────────────────────────────────
    user_input = st.chat_input("Type your message…")
    if not user_input:
        return

    # INPUT guardrail
    gr_in = check_guardrail(user_input, "INPUT")
    if not gr_in.passed:
        with st.chat_message("assistant"):
            st.error(f"🚫 Content Safety Guardrail (INPUT) — Blocked. {gr_in.blocked_reason}")
        return

    # Add user message and display
    st.session_state.builder_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # If gather phase is complete, any chat message is treated as confirmation
    # to generate — don't re-enter the gather agent.
    if st.session_state.ready_to_generate and st.session_state.jdqi_brief:
        _run_draft(client)
        return

    # Build chat-format history.
    # The chat API requires history to start with a user message, so strip
    # any leading assistant messages (the display-only greeting seed).
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.builder_messages
    ]
    while history and history[0]["role"] == "assistant":
        history = history[1:]

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            reply, brief = gather_turn(history, client)
        st.markdown(reply)

    st.session_state.builder_messages.append({"role": "assistant", "content": reply})

    if brief is not None:
        st.session_state.jdqi_brief = brief
        st.session_state.ready_to_generate = True

    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="JD Quality Intelligence",
        page_icon="🎯",
        layout="wide",
    )

    if "jdqi_context" not in st.session_state:
        st.session_state.jdqi_context = None
    if "accepted" not in st.session_state:
        st.session_state.accepted = []

    # ── Build JD tab session state ───────────────────────────────────
    if "builder_messages" not in st.session_state:
        st.session_state.builder_messages = []
    if "jdqi_brief" not in st.session_state:
        st.session_state.jdqi_brief = None
    if "jd_document" not in st.session_state:
        st.session_state.jd_document = None
    if "ready_to_generate" not in st.session_state:
        st.session_state.ready_to_generate = False
    if "brand_color" not in st.session_state:
        st.session_state.brand_color = "#1D3557"
    if "logo_bytes" not in st.session_state:
        st.session_state.logo_bytes = None

    st.title("🎯 JD Quality Intelligence (JDQI)")
    st.caption(
        "**Claude Advisor Strategy demo** — "
        "Sonnet specialists analyse in parallel · Opus advisor consulted on-demand via tool call"
    )

    client = _get_client()

    tab1, tab2 = st.tabs(["🔍 Analyse JD", "📝 Build JD"])

    with tab1:
        # ── Input form ───────────────────────────────────────────────────
        with st.form("jd_form"):
            jd_text = st.text_area(
                "Paste your Job Description",
                height=320,
                placeholder="Paste the full JD text here…",
            )
            industry = st.selectbox("Industry", INDUSTRIES)
            submitted = st.form_submit_button(
                "Analyse JD ▶", type="primary", use_container_width=True
            )

        if submitted:
            if not jd_text.strip():
                st.warning("Please paste a job description before analysing.")
            else:
                st.session_state.jdqi_context = None
                st.session_state.accepted = []
                run_pipeline(jd_text, industry, client)

        # ── Render stored report (persists across Accept button clicks) ──
        if st.session_state.jdqi_context is not None:
            display_report(st.session_state.jdqi_context)

    with tab2:
        _build_jd_tab(client)


if __name__ == "__main__":
    main()
