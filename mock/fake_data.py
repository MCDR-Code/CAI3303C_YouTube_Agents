"""Fake world for MOCK mode: trending topics and a channel-stats simulator.

Everything here is invented so the weekly loop can run with no paid services.
Numbers are seeded, so a run is repeatable.
"""
from __future__ import annotations

import math
import random

# Each topic carries enough material for the mock scriptwriter to write a real,
# speakable script. `overclaim` is a deliberately over-confident sentence the
# mock scriptwriter puts in draft 1, so the fact-checker has something real to
# catch; `overclaim_fix` is the corrected wording.
TOPICS: list[dict] = [
    {
        "topic_id": "llm-how",
        "topic": "How large language models actually work",
        "category": "explainer",
        "demand": 0.92, "competition": 0.80,
        "hook": "Every time you type into a chatbot, it is playing a guessing game billions of times a second.",
        "points": [
            ("Tokens, not words", "A language model reads text as tokens, small chunks of words. The sentence you type becomes a list of numbers."),
            ("Predicting the next token", "The model's only job is to predict the next token. It does this again and again, and the answer appears one piece at a time."),
            ("Where the knowledge comes from", "During training the model adjusts billions of weights so its guesses match real text. Those weights are where its knowledge lives."),
        ],
        "analogy": "Think of a student who has read a whole library and is finishing your sentence, one word at a time.",
        "overclaim": "Because it read so much, the model always knows the correct answer.",
        "overclaim_fix": "Because it learned patterns, not facts, the model can sound sure and still be wrong.",
    },
    {
        "topic_id": "rag",
        "topic": "RAG explained: how chatbots read your documents",
        "category": "ai_tools",
        "demand": 0.78, "competition": 0.45,
        "hook": "Why can a chatbot answer questions about a PDF it has never seen before?",
        "points": [
            ("The problem", "A model only knows what was in its training data. Your company handbook was not in it."),
            ("Retrieve first", "Retrieval augmented generation searches your documents first and finds the few passages that match the question."),
            ("Then generate", "Those passages are pasted into the prompt, and the model writes an answer grounded in them."),
        ],
        "analogy": "It is an open-book exam. The model still writes the answer, but it gets to look at the right page first.",
        "overclaim": "With RAG, a chatbot can never make anything up.",
        "overclaim_fix": "RAG makes made-up answers much less likely, but the model can still misread a passage.",
    },
    {
        "topic_id": "agents",
        "topic": "What is an AI agent, really?",
        "category": "ai_tools",
        "demand": 0.88, "competition": 0.70,
        "hook": "Everyone is selling AI agents this year. Most people cannot say what one is.",
        "points": [
            ("A model in a loop", "An agent is a language model that runs in a loop: it decides on an action, sees the result, and decides again."),
            ("Tools", "Tools let it act on the world, like searching the web, running code, or sending an email."),
            ("Handoffs", "In a multi-agent system, each agent has one job and hands the work to the next specialist."),
        ],
        "analogy": "Picture a newsroom. A researcher, a writer, and an editor pass the same story down the line.",
        "overclaim": "Agents work completely on their own and never need a human to check them.",
        "overclaim_fix": "Good agent systems still keep a human in the loop for decisions that matter.",
    },
    {
        "topic_id": "python-first",
        "topic": "Your first Python program that uses AI",
        "category": "coding",
        "demand": 0.70, "competition": 0.55,
        "hook": "In about ten lines of Python you can call the same kind of model that powers a chatbot.",
        "points": [
            ("Install one library", "You install the OpenAI client library with pip. That is the only dependency."),
            ("Send a message", "You create a client, send a list of messages, and read back the model's reply."),
            ("Keep your key safe", "Your API key goes in an environment file, never in the code you share."),
        ],
        "analogy": "It is like sending a text message, except the reply comes from a model instead of a friend.",
        "overclaim": "This code will work with every AI provider without any changes.",
        "overclaim_fix": "Many providers accept the same format, but you may need to change the base URL and model name.",
    },
    {
        "topic_id": "hallucinations",
        "topic": "Why AI makes things up (hallucinations)",
        "category": "explainer",
        "demand": 0.81, "competition": 0.60,
        "hook": "A lawyer once filed court papers full of cases that did not exist. A chatbot wrote them.",
        "points": [
            ("Fluent is not true", "The model is trained to produce text that sounds right, which is not the same as text that is right."),
            ("Gaps get filled", "When it does not know, it fills the gap with something that fits the pattern."),
            ("How to protect yourself", "Ask for sources, check them, and use tools that ground the answer in real documents."),
        ],
        "analogy": "It is the student who never says I don't know on an exam and writes a confident paragraph anyway.",
        "overclaim": "Newer models have completely solved hallucinations.",
        "overclaim_fix": "Newer models hallucinate less often, but no model has eliminated the problem.",
    },
    {
        "topic_id": "ai-jobs",
        "topic": "Will AI take my job? A professor's honest answer",
        "category": "careers",
        "demand": 0.95, "competition": 0.85,
        "hook": "This is the question my students ask me more than any other.",
        "points": [
            ("Tasks, not jobs", "AI changes tasks inside a job long before it replaces a whole job."),
            ("Who gains", "People who learn to direct these tools tend to get more done, not less."),
            ("What to learn", "Problem framing, checking AI output, and domain knowledge stay valuable."),
        ],
        "analogy": "Spreadsheets did not end accounting. They changed what accountants spend their day on.",
        "overclaim": "AI will definitely not affect your job at all.",
        "overclaim_fix": "AI will likely change parts of most jobs, and the effect depends on the field.",
    },
    {
        "topic_id": "embeddings",
        "topic": "Embeddings: how computers understand meaning",
        "category": "explainer",
        "demand": 0.62, "competition": 0.35,
        "hook": "How does a computer know that king and queen are related, but king and carrot are not?",
        "points": [
            ("Words as points", "An embedding turns a word or a sentence into a list of numbers, a point in space."),
            ("Close means similar", "Texts with similar meaning land close together in that space."),
            ("Where it is used", "Search, recommendations, and RAG all rely on measuring that distance."),
        ],
        "analogy": "It is a map of meaning. Cities that are alike end up in the same neighborhood.",
        "overclaim": "Embeddings capture the exact meaning of any sentence perfectly.",
        "overclaim_fix": "Embeddings capture useful patterns of meaning, but they miss nuance and context.",
    },
    {
        "topic_id": "ai-ethics-bias",
        "topic": "Bias in AI: where it comes from",
        "category": "ethics_society",
        "demand": 0.58, "competition": 0.50,
        "hook": "An AI system is only as fair as the data it learned from.",
        "points": [
            ("Data reflects history", "Training data records how people behaved in the past, including unfair decisions."),
            ("Models amplify patterns", "A model can learn those patterns and repeat them at scale."),
            ("What helps", "Diverse data, testing across groups, and human review reduce the harm."),
        ],
        "analogy": "If you learn to cook only from one family's recipes, every dish tastes like that kitchen.",
        "overclaim": "Removing names from the data always removes bias.",
        "overclaim_fix": "Removing names helps, but bias can still come in through other related data.",
    },
    {
        "topic_id": "prompting",
        "topic": "Prompt engineering in five minutes",
        "category": "ai_tools",
        "demand": 0.84, "competition": 0.75,
        "hook": "The same model can give you a weak answer or a great one. The difference is the prompt.",
        "points": [
            ("Give context", "Tell the model who the answer is for and what it will be used for."),
            ("Show examples", "One or two examples of the output you want beat a paragraph of description."),
            ("Ask for a format", "Ask for a table, a list, or a word limit, and you get something you can use."),
        ],
        "analogy": "It is like briefing a new assistant on their first day. The better the briefing, the better the work.",
        "overclaim": "The right prompt guarantees a perfect answer every time.",
        "overclaim_fix": "A good prompt makes a good answer much more likely, but you still need to check it.",
    },
    {
        "topic_id": "neural-net",
        "topic": "Neural networks explained with one neuron",
        "category": "explainer",
        "demand": 0.66, "competition": 0.65,
        "hook": "Every giant AI model is built from one very simple idea, repeated billions of times.",
        "points": [
            ("One neuron", "A neuron multiplies each input by a weight, adds them up, and passes the total through a simple function."),
            ("Layers", "Stack many neurons in layers and the network can learn complex patterns."),
            ("Learning", "Training nudges the weights a little at a time to reduce the error."),
        ],
        "analogy": "Each neuron is a voter. The weights decide how much each voter's opinion counts.",
        "overclaim": "Artificial neurons work exactly like the neurons in your brain.",
        "overclaim_fix": "Artificial neurons were inspired by the brain, but they are far simpler.",
    },
    {
        "topic_id": "local-llm",
        "topic": "Run an AI model on your own computer",
        "category": "coding",
        "demand": 0.74, "competition": 0.50,
        "hook": "You do not need the cloud to run a capable language model.",
        "points": [
            ("Why local", "Running locally keeps your data private and costs nothing per message."),
            ("What you need", "A recent computer, ideally with a graphics card, and a tool like Ollama."),
            ("The trade-off", "Local models are smaller, so they are faster to run but less capable than the biggest cloud models."),
        ],
        "analogy": "It is cooking at home instead of ordering out. More control, a little more effort.",
        "overclaim": "A local model is just as capable as the largest cloud models.",
        "overclaim_fix": "Local models have improved a lot, but the largest cloud models are usually still stronger.",
    },
    {
        "topic_id": "ai-cheating",
        "topic": "AI in the classroom: cheating or learning?",
        "category": "ethics_society",
        "demand": 0.72, "competition": 0.55,
        "hook": "As a professor, I see AI in almost every assignment now. Here is how I think about it.",
        "points": [
            ("The tool is not the problem", "Using AI to skip the thinking hurts learning. Using it to check and explain can help."),
            ("Clear rules", "Students do best when the course says exactly what use is allowed."),
            ("Assessment changes", "More in-class work, oral checks, and projects that show the process."),
        ],
        "analogy": "A calculator in math class can help you learn or help you skip learning. It depends on the assignment.",
        "overclaim": "AI detectors can always tell when a student used AI.",
        "overclaim_fix": "AI detectors are unreliable and can wrongly flag honest students.",
    },
]

TOPIC_BY_ID = {t["topic_id"]: t for t in TOPICS}


def trending(week: int, seed: int, query: str = "") -> list[dict]:
    """Mock trend search: demand drifts a little each week."""
    rng = random.Random(seed * 1000 + week)
    out = []
    for t in TOPICS:
        drift = rng.uniform(-0.08, 0.08)
        demand = max(0.05, min(1.0, t["demand"] + drift))
        q = query.lower().strip()
        if q and q not in t["topic"].lower() and q not in t["category"]:
            demand *= 0.85
        out.append({
            "topic_id": t["topic_id"],
            "topic": t["topic"],
            "category": t["category"],
            "search_demand": round(demand, 2),
            "competition": t["competition"],
            "opportunity": round(demand * (1.1 - t["competition"]), 3),
            "source": "MOCK trend data",
        })
    out.sort(key=lambda r: r["opportunity"], reverse=True)
    return out


# ----------------------------------------------------------------------
# Channel stats simulator
# ----------------------------------------------------------------------

def _title_quality(title: str) -> float:
    """Mock CTR model: question and number titles do a bit better; very long ones worse."""
    q = 1.0
    if "?" in title:
        q += 0.12
    if any(ch.isdigit() for ch in title):
        q += 0.06
    if len(title) > 70:
        q -= 0.15
    return q


def simulate_day(episode: dict, upload_sim_day: int, sim_day: int, channel_subs: int,
                 cfg_econ: dict, seed: int) -> dict:
    """Return fake YouTube stats for one video on one simulated day."""
    age = sim_day - upload_sim_day
    if age < 0:
        return {}
    topic = TOPIC_BY_ID.get(episode.get("topic_id") or "", {})
    demand = topic.get("demand", 0.6)
    meta = episode.get("metadata") or {}
    title = (meta.get("titles") or [episode["topic"]])[0]
    rng = random.Random(f"{seed}-{episode['id']}-{sim_day}")

    reach = 120 + channel_subs * 0.9                      # new channel: small audience
    impressions = reach * (0.6 + demand) * math.exp(-age / 6.0) * rng.uniform(0.8, 1.25) * 6
    ctr = 0.045 * _title_quality(title) * (0.8 + 0.4 * demand) * rng.uniform(0.85, 1.15)
    views = int(impressions * ctr)
    duration_min = (episode.get("duration_sec") or 120) / 60.0
    avg_view_pct = min(0.85, 0.42 + 0.15 * demand + rng.uniform(-0.05, 0.05))
    watch_hours = views * duration_min * avg_view_pct / 60.0
    subs = int(views * rng.uniform(0.01, 0.025))

    rpm = cfg_econ["rpm_usd"].get(episode.get("category", ""), 7.0)
    monetized = cfg_econ.get("assume_monetized", True)
    revenue = (views * cfg_econ["monetized_view_share"] / 1000.0) * rpm if monetized else 0.0
    return {
        "impressions": int(impressions),
        "views": views,
        "watch_hours": round(watch_hours, 2),
        "avg_view_pct": round(avg_view_pct, 3),
        "subscribers_gained": subs,
        "revenue_usd": round(revenue, 4),
    }
