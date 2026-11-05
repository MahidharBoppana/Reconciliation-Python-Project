// Backend URL. Change this if your FastAPI server runs on a different host/port.
const API_BASE = "https://reconciliation-python-project.onrender.com";

const systemFileInput = document.getElementById("systemFile");
const bankFileInput = document.getElementById("bankFile");
const sysFileNameEl = document.getElementById("sysFileName");
const bankFileNameEl = document.getElementById("bankFileName");
const sysLabel = document.getElementById("sysLabel");
const bankLabel = document.getElementById("bankLabel");
const uploadBtn = document.getElementById("uploadBtn");
const statusEl = document.getElementById("status");
const previewSection = document.getElementById("previewSection");
const excelViewEl = document.getElementById("excel-view");
const downloadBtn = document.getElementById("downloadBtn");

// Uploaded files summary UI
const uploadedSummary = document.getElementById("uploadedSummary");
const sysUploadedItem = document.getElementById("sysUploadedItem");
const bankUploadedItem = document.getElementById("bankUploadedItem");
const sysUploadedName = document.getElementById("sysUploadedName");
const bankUploadedName = document.getElementById("bankUploadedName");

// excel-viewer is loaded globally via the CDN scripts in index.html.
const ExcelViewer = window.ExcelViewer;

let currentReport = null; // { reportId, filename }
let currentBlobUrl = null;
let filesSelected = { system: false, bank: false };

// ---------- helpers ----------

function showStatus(message, type = "info") {
  statusEl.textContent = message;
  statusEl.className = "status " + type;
  statusEl.style.display = "block";
}

function hideStatus() {
  statusEl.style.display = "none";
}

function setFileNameUI(inputEl, nameEl, labelEl, file) {
  if (file) {
    nameEl.textContent = file.name;
    nameEl.className = "file-name has-file";
    labelEl.classList.add("has-file");
  } else {
    nameEl.textContent = "No file chosen";
    nameEl.className = "file-name";
    labelEl.classList.remove("has-file");
  }
}

// Read first line of a CSV (used to detect swapped files)
function readFirstLine(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result || "";
      const firstLine = text.split("\n")[0] || "";
      resolve(firstLine);
    };
    reader.onerror = () => reject(new Error("Could not read " + file.name));
    reader.readAsText(file, "utf-8");
  });
}

// Detect if files look swapped based on headers
function detectSwapped(sysFirstLine, bankFirstLine) {
  const sysLower = sysFirstLine.toLowerCase();
  const bankLower = bankFirstLine.toLowerCase();

  const sysHasOrder = sysLower.includes("order id");
  const bankHasMerchant = bankLower.includes("merchant ref");
  const sysHasMerchant = sysLower.includes("merchant ref");
  const bankHasOrder = bankLower.includes("order id");

  // Looks swapped if system has Merchant Ref and bank has Order ID
  if (sysHasMerchant && bankHasOrder) return "swapped";
  // Looks wrong if neither matches expected headers
  if (!sysHasOrder && !bankHasMerchant) return "unclear";
  return "ok";
}

// ---------- file selection ----------

systemFileInput.addEventListener("change", async (e) => {
  const file = e.target.files[0] || null;
  setFileNameUI(systemFileInput, sysFileNameEl, sysLabel, file);
  filesSelected.system = !!file;
  hideStatus();
  previewSection.style.display = "none";
  excelViewEl.innerHTML = "";
  downloadBtn.disabled = true;
  currentReport = null;
  if (currentBlobUrl) {
    URL.revokeObjectURL(currentBlobUrl);
    currentBlobUrl = null;
  }

  // If both files selected, peek at headers to warn about swapped files
  if (file && bankFileInput.files[0]) {
    await validateHeaders();
  }
});

bankFileInput.addEventListener("change", async (e) => {
  const file = e.target.files[0] || null;
  setFileNameUI(bankFileInput, bankFileNameEl, bankLabel, file);
  filesSelected.bank = !!file;
  hideStatus();
  previewSection.style.display = "none";
  excelViewEl.innerHTML = "";
  downloadBtn.disabled = true;
  currentReport = null;
  if (currentBlobUrl) {
    URL.revokeObjectURL(currentBlobUrl);
    currentBlobUrl = null;
  }

  if (file && systemFileInput.files[0]) {
    await validateHeaders();
  }
});

async function validateHeaders() {
  try {
    const sysFirst = await readFirstLine(systemFileInput.files[0]);
    const bankFirst = await readFirstLine(bankFileInput.files[0]);
    const result = detectSwapped(sysFirst, bankFirst);

    if (result === "swapped") {
      showStatus(
        "Files may be swapped: the System file looks like a Bank file and the Bank file looks like a System file. " +
          'System CSV should contain "Order ID"; Bank CSV should contain "Merchant Ref".',
        "error",
      );
    } else if (result === "unclear") {
      showStatus(
        'Could not detect expected headers. Make sure the System CSV has "Order ID" and the Bank CSV has "Merchant Ref".',
        "error",
      );
    } else {
      hideStatus();
    }
  } catch (err) {
    // Don't block upload on read errors
    hideStatus();
  }
}

// Show uploaded file names with tick marks after successful upload
function showUploadedSummary(sysFile, bankFile) {
  if (sysFile) {
    sysUploadedName.textContent = sysFile.name;
    sysUploadedItem.style.display = "flex";
  }
  if (bankFile) {
    bankUploadedName.textContent = bankFile.name;
    bankUploadedItem.style.display = "flex";
  }
  uploadedSummary.style.display = "grid";
}

// ---------- upload / reconcile ----------

uploadBtn.addEventListener("click", async () => {
  const sysFile = systemFileInput.files[0];
  const bankFile = bankFileInput.files[0];

  if (!sysFile || !bankFile) {
    showStatus("Please select both CSV files.", "error");
    return;
  }

  if (
    !sysFile.name.toLowerCase().endsWith(".csv") ||
    !bankFile.name.toLowerCase().endsWith(".csv")
  ) {
    showStatus("Both files must be CSV.", "error");
    return;
  }

  uploadBtn.disabled = true;
  uploadBtn.textContent = "Reconciling...";
  previewSection.style.display = "none";
  excelViewEl.innerHTML = "";
  downloadBtn.disabled = true;
  uploadedSummary.style.display = "none";
  hideStatus();

  const formData = new FormData();
  formData.append("system_file", sysFile);
  formData.append("bank_file", bankFile);

  try {
    const res = await fetch(`${API_BASE}/api/reconcile`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      let detail = "";
      try {
        detail = (await res.json()).detail || "";
      } catch (_) {}

      throw new Error(detail || `Server error (${res.status})`);
    }

    // Receive Excel file as Blob
    const blob = await res.blob();

    currentReport = {
      filename: "payout_reconciliation.xlsx",
    };

    showStatus("Reconciliation completed successfully.", "success");

    showUploadedSummary(sysFile, bankFile);

    previewSection.style.display = "block";

    // Preview the received Excel file directly
    await loadPreview(blob);
  } catch (err) {
    showStatus(err.message || "Unexpected error occurred.", "error");
    console.error(err);
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Reconcile & Upload";
  }
});

// ---------- preview ----------

async function loadPreview(blob) {
  excelViewEl.innerHTML = "";
  downloadBtn.disabled = true;

  showStatus("Loading Excel preview...", "info");

  try {
    // Convert Blob into ArrayBuffer
    const arrayBuffer = await blob.arrayBuffer();

    // Pass binary data directly to ExcelViewer
    new ExcelViewer("#excel-view", arrayBuffer, {
      theme: "light",
      lang: "en",
      themeBtn: true,
    });

    showStatus("Preview loaded successfully.", "success");

    setupDownload(blob);
  } catch (err) {
    showStatus("Preview failed: " + err.message, "error");
    console.error(err);
  }
}

// ---------- download ----------

function setupDownload(blob) {
  downloadBtn.disabled = false;

  downloadBtn.onclick = () => {
    const date = new Date().toLocaleDateString("en-GB").replaceAll("/", "-");

    const name = `reconciliation-${date}.xlsx`;

    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = name;

    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
  };
}
