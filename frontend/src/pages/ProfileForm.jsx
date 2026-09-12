import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import Shell from "../components/Shell";
import { Button, Choice, Field, Input, Notice, Select, Toggle } from "../components/ui";
import { useAsync } from "../lib/useAsync";
import {
  OCCUPATIONS, STATES, VEHICLE_TYPES, emptyProfile, toQuoteBody, validateStep,
} from "../lib/profileOptions";

const STEPS = ["You", "Where and what you do", "Money", "What you own", "Contact"];

export default function ProfileForm() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(emptyProfile);
  const [errors, setErrors] = useState({});

  const set = (field) => (value) => {
    setForm((f) => ({ ...f, [field]: value }));
    setErrors((e) => ({ ...e, [field]: undefined }));
  };
  const onInput = (field) => (event) => set(field)(event.target.value);

  const submit = useAsync(async () => {
    const quote = await api.createQuote(toQuoteBody(form));
    navigate(`/quotes/${quote.quote_id}`, { state: { quote } });
  });

  function next() {
    const found = validateStep(step, form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      window.scrollTo({ top: 0 });
    } else {
      submit.run();
    }
  }

  return (
    <Shell journey>
      <div className="mb-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex grow gap-1.5" role="presentation">
            {STEPS.map((name, index) => (
              <span
                key={name}
                className={`h-1.5 flex-1 rounded-full ${index <= step ? "bg-ochre-500" : "bg-ink/15"}`}
              />
            ))}
          </div>
          <span className="shrink-0 text-sm text-ink-soft">{step + 1} of {STEPS.length}</span>
        </div>
        <h1 className="mt-5 font-display text-3xl font-extrabold leading-tight sm:text-4xl">{STEPS[step]}</h1>
      </div>

      <div className="space-y-5">
        {step === 0 && (
          <>
            <Field label="Your name" id="full_name" error={errors.full_name}>
              <Input id="full_name" value={form.full_name} onChange={onInput("full_name")}
                     autoComplete="name" placeholder="e.g. Chiamaka Eze" />
            </Field>
            <Field label="Gender" error={errors.gender}>
              <Choice name="gender" value={form.gender} onChange={set("gender")}
                      options={[{ value: "Female", label: "Female" }, { value: "Male", label: "Male" }]} />
            </Field>
            {/* Two short fields sit side by side once there's room for them. */}
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Age" id="age" error={errors.age}>
                <Input id="age" type="number" inputMode="numeric" min="18" max="100"
                       value={form.age} onChange={onInput("age")} placeholder="e.g. 34" />
              </Field>
              <Field label="People who depend on you"
                     hint="Children, parents or anyone you support.">
                <Input type="number" inputMode="numeric" min="0" max="20"
                       value={form.dependents} onChange={onInput("dependents")} />
              </Field>
            </div>
            <Field label="Marital status" error={errors.marital_status}>
              <Choice value={form.marital_status} onChange={set("marital_status")}
                      options={[{ value: "Single", label: "Single" }, { value: "Married", label: "Married" }]} />
            </Field>
          </>
        )}

        {step === 1 && (
          <>
            <Field label="State" id="state" error={errors.state}>
              <Select id="state" value={form.state} onChange={onInput("state")}>
                <option value="">Choose your state</option>
                {Object.entries(STATES).map(([zone, states]) => (
                  <optgroup key={zone} label={zone}>
                    {states.map((state) => <option key={state} value={state}>{state}</option>)}
                  </optgroup>
                ))}
              </Select>
            </Field>
            <Field label="Where you live" error={errors.area_type}>
              <Choice value={form.area_type} onChange={set("area_type")}
                      options={[
                        { value: "Urban", label: "Town or city" },
                        { value: "Rural", label: "Village or rural area" },
                      ]} />
            </Field>
            <Field label="What you do" id="occupation" error={errors.occupation}
                   hint="Pick the closest match.">
              <Select id="occupation" value={form.occupation} onChange={onInput("occupation")}>
                <option value="">Choose your work</option>
                {OCCUPATIONS.map((o) => <option key={o.value} value={o.value}>{o.value}</option>)}
              </Select>
            </Field>
            <Toggle label="I run a shop or small business"
                    hint="So we can look at cover for your stock and equipment."
                    checked={form.runs_shop} onChange={set("runs_shop")} />
          </>
        )}

        {step === 2 && (
          <>
            <Field label="What you earn in a month" id="income" error={errors.monthly_income_ngn}
                   hint="Roughly is fine. We use it to rule out anything you can't comfortably afford, and we never share it.">
              <Input id="income" type="number" inputMode="numeric" min="0" step="1000"
                     value={form.monthly_income_ngn} onChange={onInput("monthly_income_ngn")}
                     placeholder="e.g. 120000" />
            </Field>
            <Notice>
              You can leave this blank. We'll still recommend cover, but we won't be able to tell you
              what fits your budget.
            </Notice>
            <Toggle label="My employer already gives me health cover (HMO)"
                    hint="We won't push health plans you'd be paying for twice."
                    checked={form.employer_hmo} onChange={set("employer_hmo")} />
          </>
        )}

        {step === 3 && (
          <>
            <Field label="Your home" error={errors.home_status}>
              <Choice columns={1} value={form.home_status} onChange={set("home_status")}
                      options={[
                        { value: "Owner", label: "I own it" },
                        { value: "Renter", label: "I rent it" },
                        { value: "Family house", label: "I live in a family house" },
                      ]} />
            </Field>
            {form.home_status === "Owner" && (
              <Field label="Roughly what is the building worth?" error={errors.property_value_ngn}>
                <Input type="number" inputMode="numeric" min="0" step="100000"
                       value={form.property_value_ngn} onChange={onInput("property_value_ngn")}
                       placeholder="e.g. 20000000" />
              </Field>
            )}

            <Toggle label="I own a vehicle" hint="Third-party motor cover is required by law in Nigeria."
                    checked={form.owns_vehicle} onChange={set("owns_vehicle")} />
            {form.owns_vehicle && (
              <div className="space-y-5 rounded-xl border border-ink/15 bg-white/60 p-4">
                <Field label="Type" error={errors.vehicle_type}>
                  <Select value={form.vehicle_type} onChange={onInput("vehicle_type")}>
                    <option value="">Choose the type</option>
                    {VEHICLE_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                  </Select>
                </Field>
                <Field label="Year it was made" error={errors.vehicle_year}>
                  <Input type="number" inputMode="numeric" min="1970" max={new Date().getFullYear() + 1}
                         value={form.vehicle_year} onChange={onInput("vehicle_year")} placeholder="e.g. 2018" />
                </Field>
                <Field label="Roughly what is it worth today?" error={errors.vehicle_value_ngn}>
                  <Input type="number" inputMode="numeric" min="0" step="100000"
                         value={form.vehicle_value_ngn} onChange={onInput("vehicle_value_ngn")}
                         placeholder="e.g. 9000000" />
                </Field>
                <Field label="How you use it" error={errors.vehicle_use}>
                  <Choice value={form.vehicle_use} onChange={set("vehicle_use")}
                          options={[
                            { value: "Private", label: "Private" },
                            { value: "Commercial", label: "For business" },
                          ]} />
                </Field>
              </div>
            )}

            <Toggle label="I'm planning to travel abroad in the next 12 months"
                    checked={form.travelling_abroad} onChange={set("travelling_abroad")} />
            {form.travelling_abroad && (
              <Field label="How many trips?">
                <Input type="number" inputMode="numeric" min="1" max="50"
                       value={form.foreign_trips_per_year || 1} onChange={onInput("foreign_trips_per_year")} />
              </Field>
            )}
          </>
        )}

        {step === 4 && (
          <>
            <Field label="Email" id="email" error={errors.email}
                   hint="Where your policy certificate goes.">
              <Input id="email" type="email" inputMode="email" autoComplete="email"
                     value={form.email} onChange={onInput("email")} placeholder="you@example.com" />
            </Field>
            <Field label="Phone number" id="phone" hint="Optional. Only used if a broker needs to reach you.">
              <Input id="phone" type="tel" inputMode="tel" autoComplete="tel"
                     value={form.phone} onChange={onInput("phone")} placeholder="08012345678" />
            </Field>
            <Notice title="What happens next">
              We'll show you what suits you, what it costs, and what we've ruled out and why.
              Nothing is bought until you choose to pay.
            </Notice>
          </>
        )}

        {submit.error && <Notice tone="warn" title="That didn't go through">{submit.error}</Notice>}

        <div className="flex gap-3 pt-2">
          {step > 0 && (
            <Button variant="quiet" onClick={() => setStep(step - 1)} disabled={submit.pending}>
              Back
            </Button>
          )}
          <Button onClick={next} disabled={submit.pending} className="flex-1 sm:flex-none sm:px-10">
            {submit.pending ? "Working it out…" : step === STEPS.length - 1 ? "See what suits me" : "Continue"}
          </Button>
        </div>
      </div>
    </Shell>
  );
}