function loadOverview() {
  const content = document.getElementById("content");

  content.innerHTML = `
    <div class="layout">

      <div class="flow">

        <div class="card">
          <h3>Deal Overview</h3>

          <div class="kpi-row">
            <div class="kpi"><h4>Total Deals</h4><div>128</div></div>
            <div class="kpi"><h4>Active Pipelines</h4><div>42</div></div>
            <div class="kpi"><h4>Conversions</h4><div>18%</div></div>
          </div>
        </div>

        <div class="card">
          <h3>Revenue Trend</h3>
          <canvas id="revenueChart"></canvas>
        </div>

        <div class="card">
          <h3>Recent Activity</h3>
          <div class="timeline">
            <div>✔ Investor replied → <span class="green">Interested</span></div>
            <div>📄 Pitch deck uploaded</div>
            <div>⚙ Draft generated</div>
            <div>📅 Meeting scheduled</div>
          </div>
        </div>

      </div>

      <div class="panel">

        <div class="card">
          <h3>AI Signals</h3>
          <p>✔ Strong investor intent detected</p>
          <p>✔ High response probability</p>
          <p>⚠ Follow-up in 2 days</p>
        </div>

        <div class="card">
          <h3>Quick Actions</h3>
          <button onclick="showToast('Draft Generated')">Generate Draft</button>
        </div>

      </div>

    </div>
  `;

  // Prevent duplicate charts
  if (window.revenueChartInstance) {
    window.revenueChartInstance.destroy();
  }

  requestAnimationFrame(() => {
    const ctx = document.getElementById("revenueChart");

    if (!ctx) return;

    window.revenueChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: ["Jan", "Feb", "Mar", "Apr", "May"],
        datasets: [{
          data: [12000, 19000, 15000, 22000, 26000],
          borderColor: "#38bdf8",
          borderWidth: 2,
          tension: 0.4
        }]
      },
      options: {
        animation: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: { ticks: { color: "#94a3b8" } },
          y: { ticks: { color: "#94a3b8" } }
        }
      }
    });
  });
}