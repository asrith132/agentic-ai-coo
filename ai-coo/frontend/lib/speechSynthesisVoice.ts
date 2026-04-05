/**
 * Pick a Speech Synthesis voice for the assistant (browser TTS).
 *
 * Configure via .env.local (rebuild dev server after changes):
 * - NEXT_PUBLIC_TTS_VOICE_URI — exact `SpeechSynthesisVoice.voiceURI` (most precise)
 * - NEXT_PUBLIC_TTS_VOICE_NAME — case-insensitive substring match on `name`
 * - NEXT_PUBLIC_TTS_VOICE_LANG — BCP 47 prefix, default "en" (e.g. "en-GB")
 *
 * To list voices in the browser console: `speechSynthesis.getVoices().forEach(v => console.log(v.name, v.voiceURI, v.lang))`
 */
export function pickAssistantVoice(
  voices: SpeechSynthesisVoice[],
): SpeechSynthesisVoice | null {
  if (!voices.length) return null;

  const uriHint = process.env.NEXT_PUBLIC_TTS_VOICE_URI?.trim();
  if (uriHint) {
    const exact = voices.find((v) => v.voiceURI === uriHint);
    if (exact) return exact;
  }

  const nameHint = process.env.NEXT_PUBLIC_TTS_VOICE_NAME?.trim().toLowerCase();
  if (nameHint) {
    const byName = voices.find((v) => v.name.toLowerCase().includes(nameHint));
    if (byName) return byName;
  }

  const langPrefix = (
    process.env.NEXT_PUBLIC_TTS_VOICE_LANG ?? "en"
  ).toLowerCase();
  const inLang = voices.filter((v) =>
    (v.lang ?? "").toLowerCase().startsWith(langPrefix),
  );
  const pool = inLang.length ? inLang : voices;

  const localFirst = [...pool].sort((a, b) => {
    const la = a.localService === true ? 0 : 1;
    const lb = b.localService === true ? 0 : 1;
    return la - lb;
  });

  return localFirst[0] ?? null;
}
