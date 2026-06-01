function loadCompliance() {
  document.getElementById("content").innerHTML = `
    <div class="card">
      <h3>Compliance & ESG</h3>
      <div id="c">Loading...</div>
    </div>
  `;

  fetch("http://127.0.0.1:8000/compliance")
    .then(res => res.json())
    .then(data => {
      document.getElementById("c").innerHTML = `
        Risk: ${data.risk}<br>
        ESG: ${data.esg}<br>
        ${data.note}
      `;
    })
    .catch(() => {
      document.getElementById("c").innerText = "Error loading compliance data";
    });
}