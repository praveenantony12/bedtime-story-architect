import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, TypedDict

from groq import Groq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

Phase = Literal[
    "greeting",
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
    "Sound warm, gentle, and loving - like a caring parent or grandparent at bedtime. "
    "Keep each response gentle and easy to follow."
)

SLEEPY_SYSTEM_PROMPT = """
You are a 'Sleepy Story Friend' — a warm, hushed, and deeply cozy bedtime storyteller for young children.
Your goal is to gently narrate a calming story that helps the child relax and drift off to sleep.

VOICE SYNTHESIS RULES (CRITICAL):
1. Write as you speak — use natural contractions: it's, you're, let's, we're, won't, can't.
2. Use ELLIPSES (...) GENEROUSLY - place them after every few words so the listener has time to picture the scene.
3. Use DASHES (—) for a soft, sleepy breath between thoughts.
4. NEVER use symbols, emojis, asterisks, hashtags, or bullet points.
5. Spell out ALL numbers: write 'three' not '3'.
6. Keep responses to SEVEN or EIGHT short, simple sentences - speak slowly, leave room for silence.

NARRATIVE STYLE:
- Narrate in a very slow, whispering, lullaby like voice.
- Picture yourself sitting beside the child who is already half asleep.
- Use simple words that are easy for a tired mind to follow.
- Pause often with ellipses so the child can paint the picture in their mind.
- Gradually lower the energy of each segment - get quieter, slower, and dreamier as the story continues.
- Use gentle 'sleep words': moonlight, soft, cozy, snuggly, quiet, dreamy, twinkling, glowing, peaceful, gentle, calm, sleepy, drowsy.
- If the kid says 'yes' for more, gently continue. If 'no', give a loving sleepy farewell and end the story.
"


def _remove_question_sentences(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    pieces = re.split(r"(?<=[.!?])\s+", cleaned)
    kept = [segment for segment in pieces if "?" not in segment]
    result = " ".join(kept).strip()
    if not result and "?" in cleaned:
        result = cleaned.split("?", 1)[0].strip()
    return result


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
            # Ask the LLM for the warm greeting ONLY - no question.
            # We append the story question ourselves so it is always present
            # and always separated from the greeting by a clear ellipsis pause
            raw = self._llm(
                system=(
                    VOICE_RULES + "\n\n"
                    "You are a warm and loving bedtime storyteller. "
                    "Write ONLY a warm personal greeting for the child using their name. "
                    "Make them feel special and welcomed. "
                    "Do NOT ask any question. Do NOT mention stories. "
                    "One or two short sentences only."
                ),
                user=(
                    f"Child's name: {child_name}. "
                    "Return ONLY valid JSON with the greeting alone: "
                    f'{{"greeting": "warm personal greeting using the child\'s name: {child_name}"}}'
                ),
            )
            data = self._parse_json(raw)
            greeting = data.get("greeting", f"Hello {child_name}... It's so wonderful to see you tonight...")
            greeting = _remove_question_sentences(greeting)
            if not greeting:
                greeting = f"Hello {child_name}... It's so wonderful to see you tonight..."
            # Hardcode the pause + question here so it always comes after the greeting with a clear separation
            narration = f"{greeting} ... What kind of story would you like to hear tonight?"
            return {
                **state,
                "phase": "storytelling",
                "narration": narration,
                "image_prompt": "a magical glowing storybook opening under a starry night sky",
                "question_for_kid": "",
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
                    + f"You are a gentle bedtime storyteller whispering a soothing story to a {age}-year-old named {child_name}. "
                    "Narrate very slowly, as if the child is already drowsy and drifting to sleep. "
                    "Use frequent ellipses (...) so the words flow with natural, sleepy pauses. "
                    "Keep each segment to SEVEN or EIGHT short sentences so each scene feels complete. "
                    "Use simple, peaceful, vivid images - moonlight, soft glowing stars, cozy blankets, gentle animals, quiet forests, twinkling fireflies, soft clouds, shimmering lakes, magical doors, sleepy villages, etc. "
                    "Weave the child's ideas into the story when they speak. "
                    "After two to four segments total, bring the story to a calm and satisfying close. "
                    "Keep language simple and age-appropriate."
                ),
                user=(
                    f"Story so far:\n{story_so_far or '(none yet)}'\n\n"
                    f"{situation}\n\n"
                    "Return ONLY valid JSON:\n"
                    "{\n"
                    '  "narration": "the next story segment, seven to eight short sentences",\n'
                    '  "image_prompt": "a short vivid illustration description for this scene",\n'
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
                "story_so_far": updated_story,
                "narration": narration,
                "image_prompt": data.get("image_prompt", ""),
                "is_story_finished": is_finished,
            }
