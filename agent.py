import json
import os
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, TypedDict

from groq import Groq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

Phase = Literal[
    "greeting",
    "warmup_q2",
    "story_request",
    "storytelling",
    "want_more",
    "ending",
]


VOICE_RULES = (
    "IMPORTANT — this text will be read aloud by a friendly voice to a young child. "
    "Write exactly as you would speak: use natural contractions (it's, you're, let's, that's). "
    "Use ellipses (...) for a cozy one-second pause. "
    "Use em-dashes (—) for a quick breath. "
    "NEVER use emojis, hashtags, asterisks, bullet points, or any symbols. "
    "Spell out all numbers as words (e.g. 'three' not '3'). "
    "Sound warm, giggly, and genuinely excited — like a fun aunt or uncle telling a story. "
    "Keep each response to two or three sentences maximum."
)

SLEEPY_SYSTEM_PROMPT = """
You are a 'Sleepy Story Friend' — a warm, playful, and cozy bedtime companion for young children.
Your goal is to be interactive, gently funny, and progressively calming.

VOICE SYNTHESIS RULES (CRITICAL):
1. Write as you speak — use natural contractions: it's, you're, let's, we're, won't, can't.
2. Use ELLIPSES (...) for cozy one-second pauses between ideas.
3. Use DASHES (—) for a quick, warm breath.
4. NEVER use symbols, emojis, asterisks, hashtags, or bullet points.
5. Spell out ALL numbers: write 'three' not '3'.
6. Keep responses short: two to four spoken sentences so the voice loop feels snappy and alive.

PERSONALITY:
- You sound like a warm, slightly silly, very loving storyteller who LOVES this child.
- Sprinkle in little giggles, surprise, and wonder in your word choices.
- As the story goes on, get progressively softer, slower, and cozier.
- Use gentle 'yawn words' toward the end: moonlight, soft, cozy, snuggly, quiet, dreamy.
- If the kid says 'yes' for more, explode with excitement! If 'no', give a loving sleepy farewell.
"""


class StoryState(TypedDict, total=False):
    child_name: str
    age: int
    phase: Phase
    kid_input: str
    story_so_far: str
    narration: str
    image_prompt: str
    question_for_kid: str
    is_story_finished: bool
    moral: str
    goodnight_message: str


@dataclass
class BedtimeStoryAgent:
    model: str = "llama-3.3-70b-versatile"
    _client: Groq = field(init=False, repr=False)
    _graph: Any = field(init=False, repr=False)
    checkpointer: MemorySaver = field(default_factory=MemorySaver, repr=False)

    def __post_init__(self) -> None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set.")
        self._client = Groq(api_key=api_key)
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(StoryState)
        graph.add_node("conductor", self._conductor_node)
        graph.set_entry_point("conductor")
        graph.set_finish_point("conductor")
        return graph.compile(checkpointer=self.checkpointer)

    def _llm(self, system: str, user: str, temperature: float = 0.8, max_tokens: int = 600) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    def _parse_json(self, raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _conductor_node(self, state: StoryState) -> StoryState:
        phase: Phase = state.get("phase", "greeting")
        child_name = state.get("child_name", "friend")
        age = state.get("age", 6)
        kid_input = (state.get("kid_input") or "").strip()
        story_so_far = state.get("story_so_far", "")

        if phase == "greeting":
            raw = self._llm(
                system=(
                    VOICE_RULES + "\n\n"
                    "You are a magical, playful bedtime storyteller for kids. "
                    "Keep sentences short and super fun. "
                    "Warmly greet the child by name only with great warmth and excitement, "
                    "then ask ONE silly funny question to get them giggling. Keep it under 60 words. "
                    "Do NOT mention their age."
                ),
                user=(
                    f"Child's name: {child_name}. "
                    "Greet them warmly by name and ask one funny warm-up question. "
                    "Return ONLY valid JSON: "
                    '{"narration": "greeting + funny question", "question_for_kid": "the question alone"}'
                ),
            )
            data = self._parse_json(raw)
            return {
                **state,
                "phase": "warmup_q2",
                "narration": data.get("narration", f"Hello {child_name}! Ready for a story?"),
                "image_prompt": "a magical glowing storybook opening under a starry night sky",
                "question_for_kid": data.get("question_for_kid", ""),
                "is_story_finished": False,
                "moral": "",
                "goodnight_message": "",
            }

        if phase == "warmup_q2":
            raw = self._llm(
                system=(
                    VOICE_RULES + "\n\n"
                    "You are a playful bedtime storyteller for kids. "
                    "React briefly and enthusiastically to the child's answer, "
                    "then ask one more short, funny question. Keep it under 50 words."
                ),
                user=(
                    f"Child: {child_name}, age: {age}. Their answer: {kid_input!r}. "
                    "React and ask another funny question. "
                    "Return ONLY valid JSON: "
                    '{"narration": "reaction + new funny question", "question_for_kid": "the question alone"}'
                ),
            )
            data = self._parse_json(raw)
            return {
                **state,
                "phase": "story_request",
                "narration": data.get("narration", "Haha! That is amazing!"),
                "image_prompt": "stars twinkling and a happy child laughing in a cozy bed",
                "question_for_kid": data.get("question_for_kid", "What kind of story would you like tonight?"),
                "is_story_finished": False,
                "moral": "",
                "goodnight_message": "",
            }

        if phase == "story_request":
            raw = self._llm(
                system=(
                    VOICE_RULES + "\n\n"
                    "You are a warm bedtime storyteller. The child has answered your fun warm-up questions. "
                    "React briefly to their last answer, then ask them what story they would like. "
                    "Keep it under 40 words, make it exciting."
                ),
                user=(
                    f"Child: {child_name}, age: {age}. Last answer: {kid_input!r}. "
                    "Ask what story they would like tonight. "
                    "Return ONLY valid JSON: "
                    '{"narration": "bridging text + story question", "question_for_kid": "the question alone"}'
                ),
            )
            data = self._parse_json(raw)
            return {
                **state,
                "phase": "storytelling",
                "narration": data.get("narration", "So, what story shall we tell tonight?"),
                "image_prompt": "a magical path leading into an enchanted forest under moonlight",
                "question_for_kid": data.get("question_for_kid", "What story would you like tonight?"),
                "is_story_finished": False,
                "moral": "",
                "goodnight_message": "",
                "story_so_far": "",
            }

        if phase == "storytelling":
            is_fresh = not story_so_far.strip()
            if is_fresh and not (kid_input or "").strip():
                # Waiting for the kid to tell us what story they want — nudge gently
                return {
                    **state,
                    "phase": "storytelling",
                    "story_so_far": "",
                    "narration": (
                        f"So {child_name}, what kind of story do you want tonight? "
                        "A dragon adventure? A space explorer? A magical princess? You choose!"
                    ),
                    "image_prompt": "a magical glowing book floating open under a starry sky",
                    "question_for_kid": "What kind of story would you like?",
                    "is_story_finished": False,
                    "moral": "",
                    "goodnight_message": "",
                }
            if is_fresh:
                situation = f"Start a new story based on the child's request: {kid_input!r}."
            elif not (kid_input or "").strip():
                situation = "Continue the story naturally and excitingly with the next segment. Do not pause for input."
            else:
                situation = f"Continue the story. The child just said: {kid_input!r}. Weave their words into the story naturally."
            raw = self._llm(
                system=(
                    SLEEPY_SYSTEM_PROMPT
                    + f"You are a magical bedtime storyteller for a {age}-year-old named {child_name}. "
                    "Tell the story in short vivid sentences that sound natural when spoken aloud. "
                    "Each segment should be three to five sentences. "
                    "Weave the child's ideas into the story when they speak. "
                    "After three to five segments total the story should reach a natural satisfying end. "
                    "Keep language age-appropriate and warm."
                ),
                user=(
                    f"Story so far:\n{story_so_far or '(none yet)'}\n\n"
                    f"{situation}\n\n"
                    "Return ONLY valid JSON:\n"
                    "{\n"
                    '  "narration": "the next story segment, three to five sentences",\n'
                    '  "image_prompt": "a short vivid illustration description for this scene",\n'
                    '  "question_for_kid": "a short optional question to engage the child, or empty string",\n'
                    '  "is_finished": true or false\n'
                    "}"
                ),
                temperature=0.75,
            )
            data = self._parse_json(raw)
            narration = data.get("narration", "And the adventure continued...")
            updated_story = f"{story_so_far}\n\n{narration}".strip()
            is_finished = bool(data.get("is_finished", False))
            return {
                **state,
                "phase": "want_more" if is_finished else "storytelling",
                "story_so_far": updated_story,
                "narration": narration,
                "image_prompt": data.get("image_prompt", "a magical story scene under the stars"),
                "question_for_kid": "Would you like to hear another story?" if is_finished else "",
                "is_story_finished": is_finished,
                "moral": "",
                "goodnight_message": "",
            }

        if phase == "want_more":
            affirmatives = {"yes", "yeah", "yep", "sure", "please", "more", "continue", "ok", "okay", "yay", "another"}
            wants_more = any(w in kid_input.lower() for w in affirmatives) if kid_input else False
            if wants_more:
                return {
                    **state,
                    "phase": "storytelling",
                    "story_so_far": "",
                    "kid_input": "",
                    "narration": f"Yay! Let's go on another adventure, {child_name}! What shall we explore next?",
                    "image_prompt": "a new magical door opening into a shimmering glowing world",
                    "question_for_kid": "What kind of story would you like next?",
                    "is_story_finished": False,
                    "moral": "",
                    "goodnight_message": "",
                }
            else:
                raw = self._llm(
                    system=(
                        SLEEPY_SYSTEM_PROMPT
                        + "You are a warm loving bedtime storyteller wrapping up the evening."
                    ),
                    user=(
                        f"Story that was just told:\n{story_so_far}\n\n"
                        f"Child: {child_name}, age: {age}. "
                        "Give a beautiful one-sentence moral and a warm loving goodnight message. "
                        "Return ONLY valid JSON: "
                        '{"moral": "...", "goodnight_message": "..."}'
                    ),
                    temperature=0.6,
                )
                data = self._parse_json(raw)
                moral = data.get("moral", "Always be kind and brave, and dreams will come true.")
                goodnight = data.get(
                    "goodnight_message",
                    f"Sweet dreams, {child_name}! Sleep tight and dream of great adventures.",
                )
                return {
                    **state,
                    "phase": "ending",
                    "narration": f"{moral} {goodnight}",
                    "image_prompt": "a peaceful sleeping child with a gentle smile under glowing stars and a crescent moon",
                    "question_for_kid": "",
                    "is_story_finished": True,
                    "moral": moral,
                    "goodnight_message": goodnight,
                }

        return {**state, "narration": "", "question_for_kid": ""}

    def run_turn(
        self,
        *,
        thread_id: str,
        child_name: Optional[str] = None,
        age: Optional[int] = None,
        phase: Phase = "greeting",
        kid_input: Optional[str] = None,
        story_so_far: Optional[str] = None,
    ) -> StoryState:
        initial_state: StoryState = {
            "child_name": child_name or "",
            "age": age or 6,
            "phase": phase,
            "kid_input": kid_input or "",
            "story_so_far": story_so_far or "",
        }
        result = self._graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}},
        )
        return result


def get_agent() -> BedtimeStoryAgent:
    if not hasattr(get_agent, "_instance"):
        setattr(get_agent, "_instance", BedtimeStoryAgent())
    return getattr(get_agent, "_instance")

