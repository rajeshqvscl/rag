/* ================= TOAST ================= */
function showToast(message, type = "info") {
  const toast = document.getElementById("toast");
  if (!toast) { console.log("[TOAST]", type + ":", message); return; }

  toast.innerText = message;
  toast.className = "toast show " + type;

  setTimeout(() => {
    if (toast) toast.className = "toast";
  }, 2500);
}


/* ================= MODAL ================= */
function showModal(content) {
  const modal = document.getElementById("modal");
  if (!modal) return;

  modal.innerHTML = `
    <div class="modal-box">
      ${content}
    </div>
  `;

  modal.style.display = "flex";
}

function closeModal() {
  const modal = document.getElementById("modal");
  if (modal) modal.style.display = "none";
}


/* ================= LOADER ================= */
function showLoader(targetId) {
  const el = document.getElementById(targetId);
  if (!el) return;
  el.innerHTML = `
    <div class="loader"></div>
  `;
}