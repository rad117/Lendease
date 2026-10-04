/* LendEase front-end script. Plain JavaScript, loaded on every page.
   Each section first checks that its elements exist, so it only runs on the page that needs it. */

// ============================================================
// Shared helpers
// ============================================================

// Same formula as calculate_emi() in app.py: EMI = P*r*(1+r)^n / ((1+r)^n - 1)
function calcEmi(principal, annualRate, months) {
  if (!(principal > 0) || !(annualRate >= 0) || !(months > 0)) {
    return null;
  }
  var r = annualRate / 12 / 100;
  var emi;
  if (r === 0) {
    emi = principal / months;
  } else {
    var growth = Math.pow(1 + r, months);
    emi = principal * r * growth / (growth - 1);
  }
  emi = Math.round(emi * 100) / 100;
  var total = Math.round(emi * months * 100) / 100;
  return { emi: emi, total: total, interest: Math.round((total - principal) * 100) / 100 };
}

// 3000000 -> ₹30,00,000 (Indian lakh/crore grouping)
function formatInr(value) {
  return '₹' + Math.round(value).toLocaleString('en-IN');
}

// Stops text from the database being treated as HTML when we build result cards.
function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// fetch() that sends the CSRF token and turns error responses into Error objects.
function fetchJson(url, options) {
  options = options || {};
  options.headers = options.headers || {};
  options.headers['X-CSRF-Token'] = document.querySelector('meta[name="csrf-token"]').content;
  if (options.body) {
    options.headers['Content-Type'] = 'application/json';
  }
  return fetch(url, options).then(function (response) {
    return response.json().then(function (data) {
      if (!response.ok) {
        throw new Error(data.error || 'Request failed (' + response.status + ')');
      }
      return data;
    });
  });
}

var loggedIn = document.body.dataset.loggedIn === 'true';

// ============================================================
// Mobile menu
// ============================================================

var navToggle = document.querySelector('.nav-toggle');
var navLinks = document.getElementById('nav-links');
if (navToggle && navLinks) {
  navToggle.addEventListener('click', function () {
    var open = navLinks.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
}

// ============================================================
// EMI calculator (home page panel and /emi-calculator)
// ============================================================

var emiForm = document.getElementById('emi-form');
if (emiForm) {
  var principalInput = document.getElementById('principal');
  var rateInput = document.getElementById('rate');
  var tenureInput = document.getElementById('tenure');
  var unitSelect = document.getElementById('tenure-unit');   // only on /emi-calculator
  var emiError = document.getElementById('emi-error');       // only on /emi-calculator

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) {
      el.textContent = text;
    }
  }

  function updateEmi() {
    var principal = parseFloat(principalInput.value);
    var rate = parseFloat(rateInput.value);
    var tenure = parseFloat(tenureInput.value);
    // The home page panel is always in years; the calculator page lets you pick months.
    var months = unitSelect && unitSelect.value === 'months' ? tenure : tenure * 12;

    // Labels next to the sliders on the home page
    setText('principal-value', formatInr(principal));
    setText('rate-value', rate + '%');
    setText('tenure-value', tenure + (tenure === 1 ? ' year' : ' years'));

    var result = calcEmi(principal, rate, Math.round(months));
    if (emiError) {
      emiError.hidden = result !== null;
    }
    if (!result) {
      setText('out-emi', '-');
      setText('out-principal', '-');
      setText('out-interest', '-');
      setText('out-total', '-');
      return;
    }

    setText('out-emi', formatInr(result.emi));
    setText('out-principal', formatInr(principal));
    setText('out-interest', formatInr(result.interest));
    setText('out-total', formatInr(result.total));
    document.getElementById('bar-principal').style.width = (principal / result.total * 100) + '%';
    document.getElementById('bar-interest').style.width = (result.interest / result.total * 100) + '%';
  }

  emiForm.addEventListener('input', updateEmi);
  emiForm.addEventListener('submit', function (event) { event.preventDefault(); });
  updateEmi();
}

// ============================================================
// Loan detail page: EMI preview for this product's rate range
// ============================================================

var loanDetail = document.getElementById('loan-detail');
if (loanDetail) {
  var detailAmount = document.getElementById('detail-amount');
  var detailTenure = document.getElementById('detail-tenure');
  var detailOutput = document.getElementById('detail-emi');

  function updateDetailEmi() {
    var amount = parseFloat(detailAmount.value);
    var months = parseInt(detailTenure.value, 10);
    var low = calcEmi(amount, parseFloat(loanDetail.dataset.minRate), months);
    var high = calcEmi(amount, parseFloat(loanDetail.dataset.maxRate), months);
    if (low && high) {
      detailOutput.textContent = formatInr(low.emi) + ' to ' + formatInr(high.emi) + ' a month';
    } else {
      detailOutput.textContent = 'Enter a valid amount and tenure';
    }
  }

  detailAmount.addEventListener('input', updateDetailEmi);
  detailTenure.addEventListener('input', updateDetailEmi);
  updateDetailEmi();
}

// ============================================================
// Compare page: send the filters to /api/compare and draw the results
// ============================================================

var compareForm = document.getElementById('compare-form');
if (compareForm) {
  var compareStatus = document.getElementById('compare-status');
  var compareResults = document.getElementById('compare-results');
  var sortSelect = document.getElementById('sort');

  // What the last search returned, kept so "Sort by" can redraw without asking the server again.
  var products = [];
  var savedIds = [];
  var searchAmount = NaN;
  var searchTenure = NaN;

  function tenureLabel(months) {
    var years = Math.floor(months / 12);
    var rest = months % 12;
    if (years === 0) {
      return rest + ' mos';
    }
    var text = years + (years === 1 ? ' yr' : ' yrs');
    return rest ? text + ' ' + rest + ' mos' : text;
  }

  function formatDate(isoDate) {
    return new Date(isoDate + 'T00:00:00').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function hasAmountAndTenure() {
    return searchAmount > 0 && searchTenure > 0;
  }

  function buildCard(p, isBest, lowestRate, highestRate) {
    // EMI at the lowest and highest rate of this product
    var emiHtml = '<p class="result-emi">Add an amount and tenure to see the EMI</p>';
    if (hasAmountAndTenure()) {
      var low = calcEmi(searchAmount, p.min_interest_rate, searchTenure);
      var high = calcEmi(searchAmount, p.max_interest_rate, searchTenure);
      emiHtml = '<p class="result-emi">Estimated EMI<strong>' + formatInr(low.emi) + ' to ' + formatInr(high.emi) + '</strong>a month</p>';
    }

    // Position of this product's rate range on a scale shared by all results
    var scale = (highestRate - lowestRate) || 1;
    var left = (p.min_interest_rate - lowestRate) / scale * 100;
    var width = (p.max_interest_rate - p.min_interest_rate) / scale * 100;

    var saved = savedIds.indexOf(p.product_id) !== -1;
    var saveButton;
    if (loggedIn) {
      saveButton = '<button type="button" class="btn btn-sm ' + (saved ? 'btn-secondary' : 'btn-primary') + '"'
        + ' data-save-offer="' + p.product_id + '" data-saved="' + saved + '">'
        + (saved ? 'Saved ✓ (click to remove)' : 'Save this offer') + '</button>';
    } else {
      saveButton = '<a class="btn btn-primary btn-sm" href="/auth/login?next=/loans/compare">Log in to save</a>';
    }

    return '<article class="result-card' + (isBest ? ' is-best' : '') + '">'
      + '<div>'
      +   '<p class="result-bank">' + escapeHtml(p.bank_name) + (isBest ? '<span class="badge">Lowest starting rate</span>' : '') + '</p>'
      +   '<h3><a href="/loans/' + p.product_id + '">' + escapeHtml(p.product_name) + '</a></h3>'
      +   '<p class="result-meta">Fee ' + p.processing_fee_percent + '%, ' + tenureLabel(p.min_tenure_months) + ' to ' + tenureLabel(p.max_tenure_months)
      +     ', ' + formatInr(p.min_amount) + ' to ' + formatInr(p.max_amount) + '</p>'
      + '</div>'
      + '<div>'
      +   '<p class="rate">' + p.min_interest_rate + '%<span> to ' + p.max_interest_rate + '%</span></p>'
      +   '<div class="range"><span style="left:' + left.toFixed(1) + '%;width:' + width.toFixed(1) + '%"></span></div>'
      + '</div>'
      + '<div class="result-side">' + emiHtml
      +   '<div class="button-row"><a class="btn btn-ghost btn-sm" href="/loans/' + p.product_id + '">Details</a>' + saveButton + '</div>'
      + '</div>'
      + '<p class="result-foot">Reference data updated ' + formatDate(p.last_updated)
      +   '. <a href="' + escapeHtml(p.source_url) + '" target="_blank" rel="noopener noreferrer">View source</a></p>'
      + '</article>';
  }

  function drawResults() {
    if (products.length === 0) {
      compareResults.innerHTML = '';
      return;
    }

    var list = products.slice();
    if (sortSelect.value === 'emi' && hasAmountAndTenure()) {
      list.sort(function (a, b) {
        return calcEmi(searchAmount, a.min_interest_rate, searchTenure).emi - calcEmi(searchAmount, b.min_interest_rate, searchTenure).emi;
      });
    } else if (sortSelect.value === 'fee') {
      list.sort(function (a, b) { return a.processing_fee_percent - b.processing_fee_percent; });
    }
    // 'rate' needs no sorting: the server already returns the lowest starting rate first.

    var lowestRate = Math.min.apply(null, products.map(function (p) { return p.min_interest_rate; }));
    var highestRate = Math.max.apply(null, products.map(function (p) { return p.max_interest_rate; }));
    var bestId = products[0].product_id;

    compareResults.innerHTML = list.map(function (p) {
      return buildCard(p, p.product_id === bestId, lowestRate, highestRate);
    }).join('');
  }

  function runSearch() {
    // Build the query string from the filled-in fields only
    var params = new URLSearchParams();
    new FormData(compareForm).forEach(function (value, key) {
      if (String(value).trim() !== '') {
        params.set(key, value);
      }
    });

    compareStatus.textContent = 'Comparing…';
    fetchJson('/api/compare?' + params.toString()).then(function (data) {
      products = data.results;
      savedIds = data.saved_ids;
      searchAmount = parseFloat(params.get('amount'));
      searchTenure = parseInt(params.get('tenure'), 10);
      compareStatus.textContent = data.count
        ? data.count + (data.count === 1 ? ' product found.' : ' products found.')
        : 'No products match these filters. Try a different amount, tenure or bank.';
      drawResults();
    }).catch(function (error) {
      products = [];
      compareResults.innerHTML = '';
      compareStatus.textContent = error.message;
    });
  }

  // Fill the form from the URL, e.g. /loans/compare?loan_type=Car%20Loan (home page links, "Run again")
  new URLSearchParams(window.location.search).forEach(function (value, key) {
    if (compareForm.elements[key]) {
      compareForm.elements[key].value = value;
    }
  });

  compareForm.addEventListener('submit', function (event) {
    event.preventDefault();
    runSearch();
  });
  sortSelect.addEventListener('change', drawResults);
  runSearch();
}

// ============================================================
// Save / remove offer buttons (compare, loan detail and dashboard pages)
// ============================================================

document.addEventListener('click', function (event) {
  var button = event.target.closest('[data-save-offer]');
  if (!button) {
    return;
  }

  var productId = button.dataset.saveOffer;
  var wasSaved = button.dataset.saved === 'true';
  var request;
  if (wasSaved) {
    request = fetchJson('/api/save-offer/' + productId, { method: 'DELETE' });
  } else {
    request = fetchJson('/api/save-offer', { method: 'POST', body: JSON.stringify({ product_id: Number(productId) }) });
  }

  button.disabled = true;
  request.then(function () {
    if (button.dataset.removeCard === 'true') {
      // Dashboard: take the whole card away
      button.closest('[data-saved-card]').remove();
      return;
    }
    var nowSaved = !wasSaved;
    button.dataset.saved = nowSaved ? 'true' : 'false';
    button.textContent = nowSaved ? 'Saved ✓ (click to remove)' : 'Save this offer';
    button.classList.toggle('btn-secondary', nowSaved);
    button.classList.toggle('btn-primary', !nowSaved);
  }).catch(function (error) {
    alert(error.message);
  }).then(function () {
    button.disabled = false;
  });
});

// ============================================================
// Admin: ask before deleting (forms with a data-confirm message)
// ============================================================

document.addEventListener('submit', function (event) {
  var message = event.target.dataset.confirm;
  if (message && !confirm(message)) {
    event.preventDefault();
  }
});

// ============================================================
// Analytics page: graphs and pie charts (Chart.js) built from /api/analytics
// ============================================================

var analyticsForm = document.getElementById('analytics-form');
if (analyticsForm && window.Chart) {
  var typeSelect = document.getElementById('a-loan-type');
  var amountInput = document.getElementById('a-amount');
  var tenureField = document.getElementById('a-tenure');
  var analyticsStatus = document.getElementById('analytics-status');
  var analyticsData = null;   // last answer from the server
  var charts = {};            // the Chart.js charts on the page, by canvas id

  // Colours. One colour for single-series charts, two for paired series,
  // and a fixed set for pie slices so a bank or loan type always keeps its colour.
  var TEAL = '#0b8f84';
  var ORANGE = '#eb6834';
  var SLICE_COLOURS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300'];
  var LOAN_TYPE_ORDER = ['Home Loan', 'Personal Loan', 'Car Loan', 'Education Loan', 'Business Loan'];

  // Look shared by every chart
  Chart.defaults.font.family = '"DM Sans", "Segoe UI", sans-serif';
  Chart.defaults.font.size = 13;
  Chart.defaults.color = '#566377';
  Chart.defaults.borderColor = '#e4ebf5';
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.legend.labels.color = '#13202f';
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    Chart.defaults.animation = false;
  }

  // Creates a chart, replacing the previous one on the same canvas.
  function drawChart(canvasId, type, data, options) {
    if (charts[canvasId]) {
      charts[canvasId].destroy();
    }
    options = options || {};
    options.responsive = true;
    options.maintainAspectRatio = false;
    charts[canvasId] = new Chart(document.getElementById(canvasId), { type: type, data: data, options: options });
  }

  // A bar chart with one series
  // formatValue is used in the tooltip, formatTick for the (shorter) axis labels.
  function drawBarChart(canvasId, labels, values, seriesName, formatValue, formatTick, horizontal) {
    var valueAxis = { beginAtZero: true, ticks: { callback: function (v) { return formatTick(v); } } };
    var labelAxis = { grid: { display: false } };
    drawChart(canvasId, 'bar', {
      labels: labels,
      datasets: [{ label: seriesName, data: values, backgroundColor: TEAL, borderRadius: 4, maxBarThickness: 36 }]
    }, {
      indexAxis: horizontal ? 'y' : 'x',
      scales: horizontal ? { x: valueAxis, y: labelAxis } : { x: labelAxis, y: valueAxis },
      plugins: {
        legend: { display: false },   // one series: the title already says what it is
        tooltip: { callbacks: { label: function (ctx) { return seriesName + ': ' + formatValue(ctx.raw); } } }
      }
    });
  }

  // A line graph with one series
  function drawLineChart(canvasId, labels, values, seriesName, colour) {
    drawChart(canvasId, 'line', {
      labels: labels,
      datasets: [{ label: seriesName, data: values, borderColor: colour, backgroundColor: colour,
                   borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, tension: 0.2 }]
    }, {
      scales: {
        x: { title: { display: true, text: 'Tenure (years)' }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { callback: function (v) { return formatInr(v); } } }
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: function (items) { return items[0].label + ' years'; },
          label: function (ctx) { return seriesName + ': ' + formatInr(ctx.raw); }
        } }
      }
    });
  }

  // A pie chart. items: [{ name, total }]. order: fixed list of names that decides each slice's colour.
  function drawPieChart(canvasId, items, order, emptyMessageId) {
    var canvas = document.getElementById(canvasId);
    var emptyMessage = document.getElementById(emptyMessageId);
    var isEmpty = items.length === 0;
    canvas.parentElement.hidden = isEmpty;
    emptyMessage.hidden = !isEmpty;
    if (isEmpty) {
      return;
    }

    var sum = 0;
    items.forEach(function (item) { sum += item.total; });
    drawChart(canvasId, 'pie', {
      // The count is part of the label, so the legend can be read without relying on colour alone
      labels: items.map(function (item) { return item.name + ' (' + item.total + ')'; }),
      datasets: [{
        data: items.map(function (item) { return item.total; }),
        backgroundColor: items.map(function (item) {
          var index = order.indexOf(item.name);
          return SLICE_COLOURS[(index === -1 ? order.length : index) % SLICE_COLOURS.length];
        }),
        borderColor: '#ffffff',
        borderWidth: 2
      }]
    }, {
      plugins: {
        legend: { position: 'right' },
        tooltip: { callbacks: { label: function (ctx) {
          return ctx.raw + ' of ' + sum + ' (' + Math.round(ctx.raw / sum * 100) + '%)';
        } } }
      }
    });
  }

  function percent(value) {
    return Number(value).toFixed(2) + '%';
  }

  // Axis labels without trailing zeros: 8 -> "8%", 0.5 -> "0.5%"
  function percentTick(value) {
    return Number(Number(value).toFixed(2)) + '%';
  }

  function drawAnalytics() {
    var products = analyticsData.products;       // sorted by starting rate, lowest first
    var amount = parseFloat(amountInput.value);
    var months = parseInt(tenureField.value, 10);
    var best = products[0];
    var banks = products.map(function (p) { return p.short_name; });   // SBI, HDFC, ... fit under the bars

    // 1. Lowest and highest rate for each bank (two series, so this one has a legend)
    drawChart('chart-rates', 'bar', {
      labels: banks,
      datasets: [
        { label: 'Lowest rate', data: products.map(function (p) { return p.min_interest_rate; }),
          backgroundColor: TEAL, borderRadius: 4, maxBarThickness: 36 },
        { label: 'Highest rate', data: products.map(function (p) { return p.max_interest_rate; }),
          backgroundColor: ORANGE, borderRadius: 4, maxBarThickness: 36 }
      ]
    }, {
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, ticks: { callback: function (v) { return v + '%'; } } }
      },
      plugins: {
        legend: { position: 'top', align: 'end' },
        tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ': ' + percent(ctx.raw); } } }
      }
    });

    // 2. Monthly EMI at each bank's starting rate
    var emis = products.map(function (p) {
      var result = calcEmi(amount, p.min_interest_rate, months);
      return result ? result.emi : 0;
    });
    drawBarChart('chart-emi', banks, emis, 'Monthly EMI', formatInr, formatInr, false);

    // 3. Principal against interest at the lowest rate (pie)
    var bestLoan = best ? calcEmi(amount, best.min_interest_rate, months) : null;
    if (bestLoan) {
      document.getElementById('split-note').textContent =
        'Total repaid ' + formatInr(bestLoan.total) + ' at ' + percent(best.min_interest_rate) + ' (' + best.bank + ').';
      drawChart('chart-split', 'doughnut', {
        labels: ['Principal (' + formatInr(amount) + ')', 'Interest (' + formatInr(bestLoan.interest) + ')'],
        datasets: [{ data: [amount, bestLoan.interest], backgroundColor: [TEAL, ORANGE], borderColor: '#ffffff', borderWidth: 2 }]
      }, {
        cutout: '55%',
        plugins: {
          legend: { position: 'bottom' },
          tooltip: { callbacks: { label: function (ctx) {
            return formatInr(ctx.raw) + ' (' + Math.round(ctx.raw / bestLoan.total * 100) + '% of the total)';
          } } }
        }
      });
    }

    // 4 and 5. How EMI and total interest change with tenure, at the lowest rate.
    //          Only tenures this loan type actually allows are shown.
    var years = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30].filter(function (y) {
      return best && y * 12 >= best.min_tenure_months && y * 12 <= best.max_tenure_months;
    });
    var emiByTenure = [];
    var interestByTenure = [];
    years.forEach(function (y) {
      var result = calcEmi(amount, best.min_interest_rate, y * 12);
      emiByTenure.push(result ? result.emi : 0);
      interestByTenure.push(result ? result.interest : 0);
    });
    drawLineChart('chart-emi-tenure', years, emiByTenure, 'Monthly EMI', TEAL);
    drawLineChart('chart-interest-tenure', years, interestByTenure, 'Total interest', ORANGE);

    // 6. Processing fee
    drawBarChart('chart-fee', banks, products.map(function (p) { return p.processing_fee_percent; }),
                 'Processing fee', percent, percentTick, false);

    // 7 and 8. Averages from the GROUP BY queries
    drawBarChart('chart-by-type',
                 analyticsData.by_type.map(function (row) { return row.loan_type.replace(' Loan', ''); }),
                 analyticsData.by_type.map(function (row) { return row.avg_rate; }),
                 'Average starting rate', percent, percentTick, false);
    drawBarChart('chart-by-bank',
                 analyticsData.by_bank.map(function (row) { return row.short_name; }),
                 analyticsData.by_bank.map(function (row) { return row.avg_rate; }),
                 'Average starting rate', percent, percentTick, true);

    // 9 and 10. What users search for and save (pies)
    var bankOrder = analyticsData.by_bank.map(function (row) { return row.bank; }).sort();
    drawPieChart('chart-searches',
                 analyticsData.searches.map(function (row) { return { name: row.loan_type, total: row.total }; }),
                 LOAN_TYPE_ORDER, 'chart-searches-empty');
    drawPieChart('chart-saved',
                 analyticsData.saved.map(function (row) { return { name: row.bank, total: row.total }; }),
                 bankOrder, 'chart-saved-empty');

    // Headline numbers
    var totalRate = 0;
    products.forEach(function (p) { totalRate += p.min_interest_rate; });
    var lowestEmi = emis.length ? Math.min.apply(null, emis) : 0;
    document.getElementById('stat-rate').textContent = best ? percent(best.min_interest_rate) : '-';
    document.getElementById('stat-rate-bank').textContent = best ? best.bank : '';
    document.getElementById('stat-emi').textContent = lowestEmi ? formatInr(lowestEmi) : '-';
    document.getElementById('stat-emi-bank').textContent = lowestEmi ? products[emis.indexOf(lowestEmi)].bank + ', a month' : 'Enter an amount and tenure';
    document.getElementById('stat-average').textContent = best ? percent(totalRate / products.length) : '-';
    document.getElementById('stat-count').textContent = products.length + ' products compared';
  }

  function loadAnalytics() {
    analyticsStatus.textContent = 'Loading…';
    fetchJson('/api/analytics?loan_type=' + encodeURIComponent(typeSelect.value)).then(function (data) {
      analyticsData = data;
      analyticsStatus.textContent = '';
      drawAnalytics();
    }).catch(function (error) {
      analyticsStatus.textContent = error.message;
    });
  }

  typeSelect.addEventListener('change', loadAnalytics);
  // Amount and tenure only change the EMI numbers, so redraw without asking the server again.
  amountInput.addEventListener('input', function () { if (analyticsData) { drawAnalytics(); } });
  tenureField.addEventListener('input', function () { if (analyticsData) { drawAnalytics(); } });
  analyticsForm.addEventListener('submit', function (event) { event.preventDefault(); });
  loadAnalytics();
}
