"""Which installed skill shapes which stage of the CFST workflow."""

STAGE_SKILLS = {
    "plan": ("brainstorming", "Explore alternative framings and falsifiable hypotheses before fixing the research plan"),
    "stress_test": ("systematic-debugging", "Find root causes of mismatches and weak coverage before proposing alternatives"),
    "grounding_audit": ("verification-before-completion", "Evidence before assertions: every claim must be backed by cited evidence"),
    "experiments": ("writing-plans", "Turn uncertainties into concrete, ordered, verifiable experiment plans"),
    "report": ("writing-guidelines", "Edit executive prose for clarity, plain voice and honest claims"),
}
