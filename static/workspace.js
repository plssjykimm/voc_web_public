"use strict";

const account = document.querySelector("#username");
const availability = document.querySelector("#available");
account?.addEventListener("input", () => { availability.textContent = ""; });
document.querySelector("[data-check]")?.addEventListener("click", async () => {
  const value = account.value.trim();
  if (!value) { account.focus(); return; }
  try {
    const response = await fetch("/signup/check?" + new URLSearchParams({username: value}));
    if (!response.ok) throw new Error();
    const result = await response.json();
    if (account.value.trim() === value) availability.textContent = result.available ? "사용 가능한 계정명입니다." : "사용할 수 없는 계정명입니다.";
  } catch { availability.textContent = "중복 확인을 다시 시도하세요."; }
});

const memberSearch = document.querySelector("#membersearch");
const reporter = document.querySelector("select[name=reporter]");
if (memberSearch && reporter) {
  const options = [...reporter.options];
  memberSearch.addEventListener("input", () => {
    const key = memberSearch.value.trim().toLocaleLowerCase();
    const matches = options.filter(option => option.textContent.toLocaleLowerCase().includes(key));
    const previous = reporter.value;
    reporter.replaceChildren(...matches);
    if (matches.some(option => option.value === previous)) reporter.value = previous;
  });
}

const picker = document.querySelector("input[type=file]");
if (picker) {
  const list = document.querySelector(".filelist");
  let files = [];
  const synchronize = () => {
    const transfer = new DataTransfer();
    files.forEach(file => transfer.items.add(file));
    picker.files = transfer.files;
    list.replaceChildren(...files.map((file, index) => {
      const row = document.createElement("li");
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "제거";
      remove.setAttribute("aria-label", file.name + " 제거");
      remove.addEventListener("click", () => { files.splice(index, 1); synchronize(); });
      row.append(document.createTextNode(file.name + " "), remove);
      return row;
    }));
  };
  picker.addEventListener("change", () => { files.push(...picker.files); synchronize(); });
  document.addEventListener("paste", event => {
    const screenshots = [...(event.clipboardData?.files || [])].filter(file => file.type.startsWith("image/"));
    if (screenshots.length) { event.preventDefault(); files.push(...screenshots); synchronize(); }
  });
}

const state = document.querySelector("[data-transition]");
if (state) {
  const toggle = () => {
    const reason = document.querySelector("[data-reason]");
    const completed = document.querySelector("[data-completed]");
    reason.hidden = !["보류", "수용 불가"].includes(state.value);
    completed.hidden = state.value !== "완료";
    for (const label of [reason, completed]) {
      const field = label.querySelector("input,textarea");
      field.required = !label.hidden;
      field.disabled = label.hidden;
    }
  };
  state.addEventListener("change", toggle);
  toggle();
}

document.querySelectorAll("[data-copy]").forEach(button => {
  button.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(button.dataset.copy); button.textContent = "복사됨"; }
    catch {
      const range = document.createRange();
      range.selectNodeContents(button.parentNode.querySelector("code"));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = "Ctrl+C로 복사";
    }
  });
});

const dialog = document.querySelector("#delete-dialog");
document.querySelectorAll("[data-delete]").forEach(button => {
  button.addEventListener("click", () => {
    const {pk, name, username} = button.dataset;
    dialog.querySelector("[data-target]").textContent = name + " (" + username + ")";
    dialog.querySelector("[name=member]").value = pk;
    dialog.querySelector("[name=confirm_name]").value = name;
    dialog.querySelector("[name=confirm_username]").value = username;
    dialog.showModal();
    dialog.querySelector("[data-close]").focus();
  });
});
dialog?.querySelector("[data-close]").addEventListener("click", () => dialog.close());

