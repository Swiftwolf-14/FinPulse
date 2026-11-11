
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

let toastTimer;

function showToast(message) {
    const toast = $('#toast');

    if (!toast) return;

    toast.textContent = message;
    toast.classList.add('show');

    clearTimeout(toastTimer);

    toastTimer = setTimeout(() => {
        toast.classList.remove('show');
    }, 3200);
}

//CHART CONFIGURATION

const chartFont = {
    family: 'Inter, system-ui, sans-serif',
    size: 10
};

const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,

    plugins: {
        legend: {
            display: false
        },

        tooltip: {
            backgroundColor: '#0b2440',
            borderColor: '#2a5277',
            borderWidth: 1,
            titleColor: '#fff',
            bodyColor: '#d9eaff',
            padding: 10,
            displayColors: true
        }
    },

    interaction: {
        intersect: false,
        mode: 'index'
    }
};

const monthNames = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
];


//LOAD FINANCIAL DATA FROM DJANGO
// Monthly financial records.

const monthlyDataElement = document.getElementById(
    'monthly-chart-data'
);

const monthlyRecords = monthlyDataElement
    ? JSON.parse(monthlyDataElement.textContent)
    : [];


// Monthly cash-flow records.

const cashFlowDataElement = document.getElementById(
    'cash-flow-chart-data'
);

const cashFlowRecords = cashFlowDataElement
    ? JSON.parse(cashFlowDataElement.textContent)
    : [];

// Current cash-flow values from Django.

const cashFlowPanel = document.getElementById(
    'cash-flow-panel'
);

const currentCashBalance = Number(
    cashFlowPanel?.dataset.cashBalance || 0
);

const averageMonthlyCashFlow = Number(
    cashFlowPanel?.dataset.averageMonthlyCashFlow || 0
);


//PREPARE MONTHLY FINANCIAL DATA
const monthlyDataMap = new Map();

monthlyRecords.forEach(record => {
    const monthKey = record.month.slice(0, 7);

    monthlyDataMap.set(monthKey, {
        revenue: Number(record.revenue || 0),
        expense: Number(record.expenses || 0)
    });
});


// Generate the last 12 months, including months
// with no financial activity.

const currentDate = new Date();

const monthlyChartData = Array.from(
    { length: 12 },
    (_, index) => {

        const monthDate = new Date(
            currentDate.getFullYear(),
            currentDate.getMonth() - 11 + index,
            1
        );

        const year = monthDate.getFullYear();

        const month = String(
            monthDate.getMonth() + 1
        ).padStart(2, '0');

        const monthKey = `${year}-${month}`;

        const values = monthlyDataMap.get(monthKey) || {
            revenue: 0,
            expense: 0
        };

        return {
            label: monthNames[monthDate.getMonth()],
            revenue: values.revenue,
            expense: values.expense,
            profit: values.revenue - values.expense
        };
    }
);


// Available chart periods.

const chartSets = {
    3: monthlyChartData.slice(-3),
    6: monthlyChartData.slice(-6),
    12: monthlyChartData
};


// REVENUE AND EXPENSE CHART


const revenueCanvas = $('#revenueChart');

let revenueChart;

function buildRevenueChart(period = 12) {

    if (!revenueCanvas) return;

    const set = chartSets[period] || chartSets[12];

    if (revenueChart) {
        revenueChart.destroy();
    }

    revenueChart = new Chart(revenueCanvas, {
        type: 'bar',

        data: {
            labels: set.map(item => item.label),

            datasets: [
                {
                    type: 'bar',
                    label: 'Revenue',

                    data: set.map(item => item.revenue),

                    backgroundColor: 'rgba(12,153,255,.86)',
                    hoverBackgroundColor: '#45c6ff',

                    borderRadius: 3,
                    borderSkipped: false,

                    barPercentage: .58,
                    categoryPercentage: .72
                },

                {
                    type: 'line',
                    label: 'Expense',

                    data: set.map(item => item.expense),

                    borderColor: '#d85be7',
                    backgroundColor: '#d85be7',
                    pointBackgroundColor: '#d85be7',

                    pointRadius: 3,
                    pointHoverRadius: 5,

                    borderWidth: 2,
                    tension: .35
                },

                {
                    type: 'line',
                    label: 'Profit',

                    data: set.map(item => item.profit),

                    borderColor: '#39e6a4',
                    backgroundColor: '#39e6a4',
                    pointBackgroundColor: '#39e6a4',

                    pointRadius: 3,
                    pointHoverRadius: 5,

                    borderWidth: 2,
                    tension: .35
                }
            ]
        },

        options: {
            ...commonOptions,

            layout: {
                padding: {
                    top: 4,
                    right: 5,
                    left: 0,
                    bottom: 0
                }
            },

            scales: {
                x: {
                    grid: {
                        color: 'rgba(65,104,143,.16)'
                    },

                    ticks: {
                        color: '#9bb4d0',
                        font: chartFont
                    },

                    border: {
                        color: '#25425f'
                    }
                },

                y: {
                    beginAtZero: true,

                    grid: {
                        color: 'rgba(65,104,143,.2)'
                    },

                    ticks: {
                        color: '#9bb4d0',
                        font: chartFont,
                        maxTicksLimit: 5
                    },

                    border: {
                        display: false
                    }
                }
            }
        }
    });
}


//GRADIENT HELPER

function makeGradient(ctx, top, bottom) {

    const gradient = ctx.createLinearGradient(
        0, 0, 0, 180
    );

    gradient.addColorStop(0, top);
    gradient.addColorStop(1, bottom);

    return gradient;
}


// PROFIT PROJECTION CHART

const projectionCanvas = $('#projectionChart');

let projectionChart;

function buildProjectionChart(months = 3) {

    if (!projectionCanvas) return;

    if (projectionChart) {
        projectionChart.destroy();
    }

    const ctx = projectionCanvas.getContext('2d');

    // Get months containing actual financial activity.

    const activeMonths = monthlyChartData.filter(
        item => item.revenue > 0 || item.expense > 0
    );

    // Keep the latest six active months for display.

    const historicalMonths = activeMonths.slice(-6);

    // Calculate average monthly profit.

    const totalProfit = activeMonths.reduce(
        (total, item) => total + item.profit,
        0
    );

    const averageMonthlyProfit = activeMonths.length
        ? totalProfit / activeMonths.length
        : 0;

    // Historical chart data.

    const historicalLabels = historicalMonths.map(
        item => item.label
    );

    const historicalProfits = historicalMonths.map(
        item => item.profit
    );

    // Generate future projection months.

    const projectionLabels = [];
    const projectionValues = [];

    const projectionDate = new Date();

    for (let i = 1; i <= months; i++) {

        const futureDate = new Date(
            projectionDate.getFullYear(),
            projectionDate.getMonth() + i,
            1
        );

        projectionLabels.push(
            futureDate.toLocaleDateString('en-KE', {
                month: 'short',
                year: 'numeric'
            })
        );

        projectionValues.push(averageMonthlyProfit);
    }

    const labels = [
        ...historicalLabels,
        ...projectionLabels
    ];

    // Create one profit projection chart.

    projectionChart = new Chart(projectionCanvas, {
        type: 'line',

        data: {
            labels,

            datasets: [
                {
                    label: 'Actual Monthly Profit',

                    data: [
                        ...historicalProfits,
                        ...Array(months).fill(null)
                    ],

                    borderColor: '#19c5fa',

                    backgroundColor: makeGradient(
                        ctx,
                        'rgba(21,185,245,.38)',
                        'rgba(21,185,245,0)'
                    ),

                    fill: true,
                    tension: 0.35,
                    pointRadius: 4,
                    borderWidth: 2.5
                },

                {
                    label: 'Projected Monthly Profit',

                    data: [
                        ...Array(
                            Math.max(historicalProfits.length - 1, 0)
                        ).fill(null),

                        ...(historicalProfits.length
                            ? [
                                historicalProfits[
                                    historicalProfits.length - 1
                                ]
                            ]
                            : []),

                        ...projectionValues
                    ],

                    borderColor: '#b968ec',
                    borderDash: [5, 5],

                    pointRadius: 3,
                    fill: false,
                    tension: 0.35,
                    borderWidth: 1.5
                }
            ]
        },

        options: {
            ...commonOptions,

            scales: {
                x: {
                    display: false
                },

                y: {
                    display: false
                }
            },

            plugins: {
                ...commonOptions.plugins,

                tooltip: {
                    ...commonOptions.plugins.tooltip,

                    callbacks: {
                        label: context =>
                            ` KSh ${Number(context.raw).toLocaleString(
                                'en-KE',
                                {
                                    maximumFractionDigits: 2
                                }
                            )}`
                    }
                }
            }
        }
    });

    // Update forecast method.

    const forecastMethod = document.getElementById(
        'forecastMethod'
    );

    if (forecastMethod) {

        forecastMethod.textContent =
            activeMonths.length >= 6
                ? 'Historical average'
                : activeMonths.length > 0
                    ? 'Historical average (limited data)'
                    : 'Insufficient financial data';
    }

    // Update projected profit immediately.

    const forecastProfit = document.getElementById(
        'forecastProfit'
    );

    if (forecastProfit) {

        const projectedProfit = averageMonthlyProfit * months;

        forecastProfit.textContent =
            `KSh ${projectedProfit.toLocaleString('en-KE', {
                maximumFractionDigits: 2
            })}`;
    }
}


//CASH FLOW CHART

const cashCanvas = $('#cashChart');

let cashChart;

function buildCashChart() {

    if (!cashCanvas) return;

    if (cashChart) {
        cashChart.destroy();
    }

    const ctx = cashCanvas.getContext('2d');

    // Historical monthly cash-flow data.

    const historicalLabels = cashFlowRecords.map(
        record => record.month
    );

    const historicalBalances = Array(
        cashFlowRecords.length
    );

    // Reconstruct historical cash balances.

    let runningBalance = currentCashBalance;

    for (let i = cashFlowRecords.length - 1; i >= 0; i--) {

        historicalBalances[i] = runningBalance;

        runningBalance -= Number(
            cashFlowRecords[i].net || 0
        );
    }

    // Generate the next three forecast months.

    const projectionLabels = [];
    const projectionValues = [];

    const forecastDate = new Date();

    for (let i = 1; i <= 3; i++) {

        const projectedDate = new Date(
            forecastDate.getFullYear(),
            forecastDate.getMonth() + i,
            1
        );

        projectionLabels.push(
            projectedDate.toLocaleDateString('en-KE', {
                month: 'short',
                year: 'numeric'
            })
        );

        projectionValues.push(
            currentCashBalance + averageMonthlyCashFlow * i
        );
    }

    cashChart = new Chart(cashCanvas, {
        type: 'line',

        data: {
            labels: [
                ...historicalLabels,
                ...projectionLabels
            ],

            datasets: [
                {
                    label: 'Historical cash balance',

                    data: [
                        ...historicalBalances,
                        ...Array(3).fill(null)
                    ],

                    borderColor: '#35e8a6',
                    backgroundColor: 'rgba(39,222,164,.15)',

                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    spanGaps: false
                },

                {
                    label: 'Projected Cash Balance',

                    data: [
                        ...Array(
                            historicalLabels.length
                        ).fill(null),

                        currentCashBalance,
                        ...projectionValues
                    ],

                    borderColor: '#60a5fa',
                    borderDash: [6, 5],

                    backgroundColor: 'transparent',

                    fill: false,
                    tension: 0.3,
                    borderWidth: 2,
                    spanGaps: true
                }
            ]
        },

        options: {
            ...commonOptions,

            scales: {
                x: {
                    display: false
                },

                y: {
                    display: false
                }
            },

            plugins: {
                ...commonOptions.plugins,

                tooltip: {
                    ...commonOptions.plugins.tooltip,

                    callbacks: {
                        label: context =>
                            ` KSh ${Number(context.raw).toLocaleString(
                                'en-KE',
                                {
                                    maximumFractionDigits: 2
                                }
                            )}`
                    }
                }
            }
        }
    });
}


//FORECAST ACCURACY STATUS

const forecastAccuracy = document.getElementById(
    'forecastAccuracy'
);

const forecastAccuracyStatus = document.getElementById(
    'forecastAccuracyStatus'
);

if (forecastAccuracy && forecastAccuracyStatus) {

    forecastAccuracy.textContent = 'Not yet available';

    forecastAccuracyStatus.textContent =
        'Insufficient forecast history';
}


// INITIALIZE DASHBOARD CHARTS

function initializeDashboardCharts() {

    if (typeof Chart === 'undefined') {
        console.error('Chart.js has not been loaded.');
        return;
    }

    buildRevenueChart(12);
    buildProjectionChart();
    buildCashChart();
}

initializeDashboardCharts();


//REVENUE CHART PERIOD BUTTONS


$$('.period').forEach(button => {

    button.addEventListener('click', () => {

        $$('.period').forEach(item => {
            item.classList.remove('active');
        });

        button.classList.add('active');

        buildRevenueChart(
            Number(button.dataset.period)
        );
    });
});


//PROFIT PROJECTION PERIOD
const projectionRange = $('#projectionRange');

if (projectionRange) {

    projectionRange.addEventListener('change', event => {

        const months = Number(event.target.value);

        buildProjectionChart(months);
    });
}

const confirmAction=$('#confirmAction');
if (confirmAction){
    confirmAction.addEventListener('click', event =>{
        event.preventDefault();
        if (dialog){
            dialog.close();
        }
        showToast(
            '${pendingAction} is a demonstration action and has not been saved.'
        );
    });
}

// HELP BUTTON

const helpButton = $('#helpBtn');

if (helpButton) {

    helpButton.addEventListener('click', () => {

        showToast(
            'Explore the dashboard, financial analysis and forecasts.'
        );
    });
}


//  MOBILE SIDEBAR


const menuToggle = $('#menuToggle');
const sidebar = $('#sidebar');

if (menuToggle && sidebar) {

    menuToggle.addEventListener('click', () => {

        sidebar.classList.toggle('open');
    });
}


// ACTIVE NAVIGATION LINKS


$$('.nav-link').forEach(link => {

    link.addEventListener('click', () => {

        $$('.nav-link').forEach(item => {
            item.classList.remove('active');
        });

        link.classList.add('active');

        if (sidebar) {
            sidebar.classList.remove('open');
        }
    });
});


// CLOSE MOBILE SIDEBAR WHEN CLICKING OUTSIDE

document.addEventListener('click', event => {

    if (
        window.innerWidth <= 680 &&
        sidebar &&
        menuToggle &&
        !sidebar.contains(event.target) &&
        !menuToggle.contains(event.target)
    ) {

        sidebar.classList.remove('open');
    }
});





        