"""Learning from remediators (docs/LEARNING_LOOP.md).

Two signals, both already produced by people doing their normal work:

* ``decisions`` - what reviewers decided about RAWRS's proposals inside the
  workspace, and what they changed on their own (the correction log).
* ``docx_diff`` - what remediators changed in Word *after* export, read from
  the finished DOCX they upload back.

``insights`` turns both into ranked, evidence-backed recommendations.
Nothing in this package changes pipeline output: it measures and recommends;
a person decides what RAWRS should do differently.
"""
