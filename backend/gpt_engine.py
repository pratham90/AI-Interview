import os
import re
from openai import OpenAI
from dotenv import load_dotenv

class GPTEngine:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv('OPENAI_API_KEY')
        self.client = OpenAI(api_key=api_key)

    def generate_response(self, question, resume_text=None, mode="global", history=None):
        if not question.strip():
            return "No question provided."
        
        import sys
        print(f"[DEBUG] generate_response called with mode={mode}, resume_text_len={len(resume_text) if resume_text else 0}")
        sys.stdout.flush()
        
        is_intro = self._is_intro_question(question)
        
        if mode == "resume":
            if not resume_text or not resume_text.strip():
                return ("Could not extract any text from the uploaded resume. If your PDF is a scanned image, try a text-based PDF or upload a .txt file instead.")
            # Smart mode: Use resume context if possible, else give a direct answer. STRONG anti-template instructions.
            # ...existing code...
            # Smart mode: Use resume context if possible, else give a direct answer. STRONG anti-template instructions.
            if is_intro:
                system_prompt = (
                    "You are an interview assistant. Write a first-person introduction using ONLY the facts found in the resume below. "
                    "If the resume does not contain enough information, answer the question directly in the user's point of view (first-person), with a practical, specific answer. "
                    "Do NOT use a template, structure, generic example, fallback message, or any instructional text. Do NOT say 'here is a template', 'sample answer', 'example', or anything similar. Only answer as the user would, based on resume facts.\n\nResume:\n" + resume_text
                )
            else:
                system_prompt = (
                    "You are an interview assistant. Answer ONLY using the resume below. If the resume does not cover the question, answer the question directly in the user's point of view (first-person), with a concise, practical, specific answer. "
                    "Do NOT use a template, structure, generic example, fallback message, or any instructional text. Do NOT say 'here is a template', 'sample answer', 'example', or anything similar. Only answer as the user would, based on resume facts.\n\nResume:\n" + resume_text
                )
            print("[DEBUG] SMART MODE PROMPT SENT TO OPENAI:\n", system_prompt[:1000])
            sys.stdout.flush()
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            if history and isinstance(history, list) and len(history) > 0:
                messages += history
            messages.append({"role": "user", "content": question})
        else:
            # Global mode: answer purely general questions
            system_prompt = (
                "You are a helpful interview assistant. Provide general interview advice, tips, and guidance. "
                "Focus on common interview questions, best practices, and general career advice. "
                "Do not reference any specific resume or personal information unless provided in the conversation."
            )
            print(f"[DEBUG] GLOBAL MODE PROMPT SENT TO OPENAI:\n{system_prompt}")
            sys.stdout.flush()
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            if history and isinstance(history, list) and len(history) > 0:
                messages += history
            messages.append({"role": "user", "content": question})

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=512,
                temperature=(0.5 if (mode == "resume" and is_intro) else (0.45 if mode == "resume" else 0.7)),
            )
            answer = response.choices[0].message.content.strip()
            # --- STRICTEST SMART MODE FILTER (ENHANCED) ---
            if mode == "resume" and resume_text and resume_text.strip():
                import re as _re
                forbidden_phrases = [
                    "as an ai language model", "as an interview assistant", "i'm sorry", "i am unable to", "i cannot answer",
                    "based on the information provided", "based on your resume", "template", "sample", "example", "generic", "fallback", "instructional", "structured", "suggested", "possible answer", "general answer", "response:",
                    "this is a template", "here is a template", "here is an example", "here is a sample", "sample response", "for example", "for instance", "let's", "in summary", "in conclusion", "overall", "as an ", "as a ", "to answer"
                ]
                template_patterns = [
                    r"^answer[:\-]", r"^template[:\-]", r"^sample answer[:\-]", r"^example[:\-]", r"^suggested answer[:\-]", r"^possible answer[:\-]", r"^response[:\-]", r"^here is", r"^this is", r"^let's", r"^to answer", r"^in summary", r"^in conclusion", r"^overall", r"^as an? ",
                ]
                def is_template(text, resume_text):
                    text = text.strip().lower()
                    if not text:
                        return True
                    if any(phrase in text for phrase in forbidden_phrases):
                        return True
                    if any(_re.match(p, text, _re.IGNORECASE) for p in template_patterns):
                        return True
                    # Block if answer contains numbered/stepwise/list structure
                    if any(text.startswith(x) for x in ["1.", "step 1", "first,", "here's a structured", "here is a structured", "here is how", "here's how", "to answer this question, you should", "to answer this question:", "here are some steps", "here are some ways", "here are some points", "here are some tips", "here are some suggestions"]):
                        return True
                    # Block if answer contains multiple numbered points or bullet points
                    if any(x in text for x in ["2.", "3.", "4.", "- ", "• "]):
                        return True
                    # Block if answer is long but does not mention any unique resume keyword
                    resume_keywords = set(w.lower() for w in _re.findall(r"[A-Za-z]{4,}", resume_text))
                    answer_words = set(w.lower() for w in _re.findall(r"[A-Za-z]{4,}", text))
                    if len(text) > 60 and len(resume_keywords & answer_words) == 0:
                        return True
                    # Block if answer starts with a generic phrase and does not mention any resume keyword
                    generic_starts = ["i am", "my name is", "i have", "i possess", "i am a", "i'm a", "i'm an"]
                    if any(text.startswith(gs) for gs in generic_starts) and len(resume_keywords & answer_words) == 0:
                        return True
                    return False
                # In Smart mode, always return the OpenAI-generated answer unless it is a template or forbidden phrase.
                # If answer is not based on resume context (no overlap with resume keywords), provide a general answer (not a template).
                forbidden = [
                    "template", "sample", "example", "generic", "fallback", "instructional", "structured", "suggested", "possible answer", "response:",
                    "this is a template", "here is a template", "here is an example", "here is a sample", "sample response", "for example", "for instance"
                ]
                # Check for forbidden phrases
                if any(f in answer.lower() for f in forbidden):
                    answer = "[Error: The answer was blocked because it looked like a template or sample. Please rephrase your question.]"
                else:
                    # Check if answer is based on resume context (overlap with resume keywords)
                    resume_keywords = set(w.lower() for w in _re.findall(r"[A-Za-z]{4,}", resume_text))
                    answer_words = set(w.lower() for w in _re.findall(r"[A-Za-z]{4,}", answer))
                    # If no overlap and resume doesn't cover the question, provide a general answer (not a template)
                    if len(resume_keywords & answer_words) == 0:
                        # General mode system prompt
                        general_prompt = (
                            "You are a helpful interview assistant. Provide a concise, practical, and specific answer to the user's question. Do not use a template, sample, or generic structure. Answer in first person as if you are the user."
                        )
                        messages = [
                            {"role": "system", "content": general_prompt},
                            {"role": "user", "content": question}
                        ]
                        try:
                            response2 = self.client.chat.completions.create(
                                model="gpt-4o",
                                messages=messages,
                                max_tokens=256,
                                temperature=0.6,
                            )
                            answer2 = response2.choices[0].message.content.strip()
                            # Block if general answer is a template
                            if any(f in answer2.lower() for f in forbidden):
                                answer = "[Error: The answer was blocked because it looked like a template or sample. Please rephrase your question.]"
                            else:
                                answer = answer2
                        except Exception as e:
                            answer = "[Error: Could not generate a general answer.]"
            print(f"[DEBUG] Answer returned (mode={mode}): {answer[:300]}")
            sys.stdout.flush()
            return answer
        except Exception as e:
            print(f"[DEBUG] Exception in generate_response: {e}")
            sys.stdout.flush()
            return "[Error: Could not generate answer.]"

    def build_prompt(self, question, resume_text, mode):
        # Kept for compatibility; main logic handled in generate_response
        if mode == "resume" and resume_text:
            return (
                "You are an interview assistant. Prefer resume facts to answer. If general, give concise guidance.\n"
                f"Resume:\n{resume_text}\n\nQuestion: {question}\nAnswer:"
            )
        else:
            return f"You are a helpful interview assistant.\nQuestion: {question}\nAnswer:"

    def _is_intro_question(self, question: str) -> bool:
        q = question.lower()
        patterns = [
            r"tell me about yourself",
            r"about yourself",
            r"introduce yourself",
            r"give .* introduction",
            r"self introduction",
            r"yourself",
        ]
        return any(re.search(p, q) for p in patterns)

