import { useState } from "react";

import { Button, Choice, Field, Input, Notice } from "./ui";
import { useAsync } from "../lib/useAsync";

/** The action panel on a queue item: pick an outcome, add a note, record it.
    Every broker action is written to the audit log, so the note matters. */
export default function ResolveForm({ options, noteLabel, submitLabel, onSubmit, onDone }) {
  const [outcome, setOutcome] = useState(options[0].value);
  const [note, setNote] = useState("");

  const save = useAsync(async () => {
    const result = await onSubmit({ outcome, note: note.trim() });
    if (result) onDone?.(result);
  });

  return (
    <div className="mt-4 space-y-3 border-t border-ink/10 pt-4">
      <Field label="What did you do?">
        <Choice columns={1} value={outcome} onChange={setOutcome} options={options} />
      </Field>
      <Field label={noteLabel} hint="Recorded in the audit log against your action.">
        <Input value={note} onChange={(event) => setNote(event.target.value)}
               placeholder="e.g. spoke to them on 12 Sept, explained the state scheme" />
      </Field>
      {save.error && <Notice tone="warn">{save.error}</Notice>}
      <Button onClick={save.run} disabled={save.pending} className="w-full sm:w-auto">
        {save.pending ? "Recording…" : submitLabel}
      </Button>
    </div>
  );
}