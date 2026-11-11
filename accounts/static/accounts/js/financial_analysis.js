document.addEventListener('DOMContentLoaded', function () {
    // MONTHLY FINANCIAL TRENDS CHART

    const monthlyDataElement = document.getElementById(
        'monthly-analysis-data'
    );

    const monthlyCanvas = document.getElementById(
        'monthlyAnalysisChart'
    );

    if (
        monthlyDataElement &&
        monthlyCanvas &&
        typeof Chart !== 'undefined'
    ) {
        try {
            const monthlyData = JSON.parse(
                monthlyDataElement.textContent
            );

            const hasFinancialData = monthlyData.some(record =>
                Number(record.revenue) !== 0 ||
                Number(record.expenses) !== 0 ||
                Number(record.profit) !== 0
            );

            if (hasFinancialData) {

                const labels = monthlyData.map(
                    record => record.month
                );

                const revenue = monthlyData.map(
                    record => Number(record.revenue)
                );

                const expenses = monthlyData.map(
                    record => Number(record.expenses)
                );

                const profit = monthlyData.map(
                    record => Number(record.profit)
                );

                new Chart(monthlyCanvas, {
                    type: 'bar',

                    data: {
                        labels: labels,

                        datasets: [
                            {
                                type: 'bar',
                                label: 'Revenue',
                                data: revenue,
                                backgroundColor: 'rgba(16, 185, 129, 0.75)',
                                borderRadius: 5
                            },
                            {
                                type: 'bar',
                                label: 'Expenses',
                                data: expenses,
                                backgroundColor: 'rgba(239, 68, 68, 0.75)',
                                borderRadius: 5
                            },
                            {
                                type: 'line',
                                label: 'Net Profit',
                                data: profit,
                                borderColor: '#60a5fa',
                                backgroundColor: '#60a5fa',
                                borderWidth: 2,
                                tension: 0.3,
                                pointRadius: 4,
                                pointHoverRadius: 6
                            }
                        ]
                    },

                    options: {
                        responsive: true,
                        maintainAspectRatio: false,

                        interaction: {
                            mode: 'index',
                            intersect: false
                        },

                        plugins: {
                            legend: {
                                position: 'top',
                                labels: {
                                    color: '#cbd5e1',
                                    usePointStyle: true,
                                    padding: 20
                                }
                            },

                            tooltip: {
                                callbacks: {
                                    label: function (context) {
                                        return `${context.dataset.label}: KSh ${
                                            Number(context.raw).toLocaleString(
                                                'en-KE',
                                                {
                                                    minimumFractionDigits: 2,
                                                    maximumFractionDigits: 2
                                                }
                                            )
                                        }`;
                                    }
                                }
                            }
                        },

                        scales: {
                            x: {
                                ticks: {
                                    color: '#94a3b8'
                                },
                                grid: {
                                    display: false
                                }
                            },

                            y: {
                                beginAtZero: true,
                                ticks: {
                                    color: '#94a3b8',
                                    callback: function (value) {
                                        return 'KSh ' +
                                            Number(value).toLocaleString('en-KE');
                                    }
                                },
                                grid: {
                                    color: 'rgba(148, 163, 184, 0.12)'
                                }
                            }
                        }
                    }
                });
            }

        } catch (error) {
            console.error(
                'Monthly financial chart initialization failed:',
                error
            );
        }
    }

    // EXPENSE CATEGORY DOUGHNUT CHART

    const expenseDataElement = document.getElementById(
        'expense-category-data'
    );

    const expenseCanvas = document.getElementById(
        'expenseCategoryChart'
    );

    if (
        expenseDataElement &&
        expenseCanvas &&
        typeof Chart !== 'undefined'
    ) {
        try {
            const expenseData = JSON.parse(
                expenseDataElement.textContent
            );

            if (expenseData.length > 0) {

                new Chart(expenseCanvas, {
                    type: 'doughnut',

                    data: {
                        labels: expenseData.map(
                            item => item.category
                        ),

                        datasets: [{
                            data: expenseData.map(
                                item => Number(item.amount)
                            ),

                            backgroundColor: [
                                '#10B981',
                                '#3B82F6',
                                '#F59E0B',
                                '#A855F7',
                                '#EF4444',
                                '#06B6D4'
                            ],

                            borderWidth: 2,
                            borderColor: '#182232'
                        }]
                    },

                    options: {
                        responsive: true,
                        maintainAspectRatio: false,

                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: {
                                    color: '#cbd5e1',
                                    padding: 15
                                }
                            },

                            tooltip: {
                                callbacks: {
                                    label: function (context) {
                                        return `${context.label}: KSh ${
                                            Number(context.raw).toLocaleString(
                                                'en-KE',
                                                {
                                                    minimumFractionDigits: 2,
                                                    maximumFractionDigits: 2
                                                }
                                            )
                                        }`;
                                    }
                                }
                            }
                        }
                    }
                });
            }

        } catch (error) {
            console.error(
                'Expense category chart initialization failed:',
                error
            );
        }
    }

});