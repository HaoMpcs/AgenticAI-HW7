# Grounded evidence criterion

Question: Does the comment cite only evidence that appears in the issue or in the
results returned by RepoMind's tools for this output?

Pass means every factual claim presented as observed evidence is supported by the
issue or a tool result. A reasonable proposal or inference is allowed when it is
clearly framed as such and its premises are supported.

Fail means the comment presents any unsupported factual claim as evidence,
including:

- a file or code fact from a file that was never read or shown by search;
- a line number that no search result showed (file reads have no line numbers);
- a test, CI, command, browser, console, or runtime result that no tool returned;
- an error message, count, endpoint response, or observed behaviour absent from
  both the issue and tool results;
- a maintainer statement, earlier request, design intent, documentation statement,
  deployment fact, or repository history that was not returned;
- a pull request identifier or write result that the tools did not return;
- certainty about a cause or affected component that requires unobserved evidence.

Do not fail merely because the proposed fix is imperfect, the classification is
debatable, or the prose is long. Judge grounding only.
