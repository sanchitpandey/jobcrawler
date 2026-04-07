/**
 * Shared DOM fixture helpers for vitest tests.
 * Tests run under jsdom (configured in vitest.config.ts).
 */

export function createMockInput(
  type: string = "text",
  id?: string
): HTMLInputElement {
  const input = document.createElement("input");
  input.type = type;
  if (id) input.id = id;
  document.body.appendChild(input);
  return input;
}

export function createMockTextarea(id?: string): HTMLTextAreaElement {
  const ta = document.createElement("textarea");
  if (id) ta.id = id;
  document.body.appendChild(ta);
  return ta;
}

export function createMockSelect(options: string[]): HTMLSelectElement {
  const select = document.createElement("select");
  // Leading placeholder so we can verify it isn't picked accidentally.
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select an option";
  select.appendChild(placeholder);
  for (const text of options) {
    const opt = document.createElement("option");
    opt.value = text.toLowerCase().replace(/\s+/g, "_");
    opt.textContent = text;
    select.appendChild(opt);
  }
  document.body.appendChild(select);
  return select;
}

export function createMockRadioGroup(
  name: string,
  options: string[]
): HTMLFieldSetElement {
  const fieldset = document.createElement("fieldset");
  for (const value of options) {
    const id = `${name}_${value.replace(/\s+/g, "_")}`;
    const label = document.createElement("label");
    label.setAttribute("for", id);
    label.textContent = value;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = name;
    radio.id = id;
    radio.value = value;
    fieldset.appendChild(radio);
    fieldset.appendChild(label);
  }
  document.body.appendChild(fieldset);
  return fieldset;
}

/** Wipe all top-level body children between tests. */
export function resetDom(): void {
  document.body.innerHTML = "";
}
