const chat = document.querySelector("#chat");
const form = document.querySelector("#composer");
const input = document.querySelector("#message");
const send = document.querySelector("#send");
let approvalPending = false;

function addCard(kind, label, content) {
  const card = document.createElement("article");
  card.className = `message ${kind}`;
  const tag = document.createElement("span");
  tag.className = "label";
  tag.textContent = label;
  const body = document.createElement("pre");
  body.textContent = content;
  card.append(tag, body);
  chat.append(card);
  card.scrollIntoView({ behavior: "smooth", block: "end" });
  return card;
}

function setBusy(busy) {
  send.disabled = busy;
  input.disabled = busy;
  send.textContent = busy ? "Working…" : "Send";
}

function showEvents(events) {
  for (const event of events) {
    if (event.type === "assistant") {
      addCard("assistant", "Agent", event.content);
    } else if (event.type === "usage") {
      addCard(
        "usage",
        "API call",
        `Input ${event.input} · Cached ${event.cached} · Output ${event.output}`,
      );
    } else if (event.type === "tool_result") {
      const state = event.approved ? "Ran command" : "Denied command";
      addCard("tool-result", state, `$ ${event.command}\n\n${event.content}`);
    } else if (event.type === "approval") {
      showApproval(event);
    }
  }
}

function showApproval(event) {
  approvalPending = true;
  setBusy(true);
  const card = addCard("approval", "Approval required", `$ ${event.command}`);
  const actions = document.createElement("div");
  actions.className = "actions";
  const approve = document.createElement("button");
  approve.textContent = "Approve";
  approve.className = "approve";
  const deny = document.createElement("button");
  deny.textContent = "Deny";
  deny.className = "deny";
  actions.append(approve, deny);
  card.append(actions);

  async function decide(approved) {
    approve.disabled = true;
    deny.disabled = true;
    const response = await fetch("/api/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Decision failed");
    approvalPending = false;
    showEvents(data.events);
    if (!approvalPending) setBusy(false);
  }

  approve.addEventListener("click", () => decide(true).catch(showError));
  deny.addEventListener("click", () => decide(false).catch(showError));
}

function showError(error) {
  addCard("error", "Error", error.message);
  setBusy(false);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  addCard("user", "You", message);
  input.value = "";
  setBusy(true);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed");
    showEvents(data.events);
  } catch (error) {
    showError(error);
  } finally {
    setBusy(approvalPending);
    input.focus();
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
