#!/usr/bin/env python3


def generate_chart_javascript():
    """Chart.js用のJavaScriptコードを生成する（室外機冷却システム用）"""
    return """
        function generateHourlyCharts() {
            // デューティサイクル 時間別パフォーマンス
            const dutyCycleCtx = document.getElementById('dutyCycleHourlyChart');
            if (dutyCycleCtx && hourlyData.hourly_stats) {
                new Chart(dutyCycleCtx, {
                    type: 'line',
                    data: {
                        labels: hourlyData.hourly_stats.map(d => d.hour + '時'),
                        datasets: [{
                            label: '平均デューティサイクル（%）',
                            data: hourlyData.hourly_stats.map(d => d.avg_duty_cycle),
                            borderColor: 'rgb(52, 152, 219)',
                            backgroundColor: 'rgba(52, 152, 219, 0.2)',
                            tension: 0.1,
                            yAxisID: 'y',
                            borderWidth: 3,
                            pointRadius: 4,
                            pointHoverRadius: 6
                        }, {
                            label: '最小デューティサイクル（%）',
                            data: hourlyData.hourly_stats.map(d => d.min_duty_cycle),
                            borderColor: 'rgb(34, 197, 94)',
                            backgroundColor: 'rgba(34, 197, 94, 0.1)',
                            tension: 0.1,
                            yAxisID: 'y',
                            borderDash: [8, 4],
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 5
                        }, {
                            label: '最大デューティサイクル（%）',
                            data: hourlyData.hourly_stats.map(d => d.max_duty_cycle),
                            borderColor: 'rgb(239, 68, 68)',
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            tension: 0.1,
                            yAxisID: 'y',
                            borderDash: [4, 4],
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 5
                        }, {
                            label: 'エラー率（%）',
                            data: hourlyData.hourly_stats.map(d => d.error_rate || 0),
                            borderColor: 'rgb(255, 99, 132)',
                            backgroundColor: 'rgba(255, 99, 132, 0.2)',
                            tension: 0.1,
                            yAxisID: 'y1'
                        }]
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
                                    usePointStyle: true,
                                    padding: 20,
                                    font: {
                                        size: 12
                                    }
                                }
                            },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                titleColor: 'white',
                                bodyColor: 'white',
                                borderColor: 'rgba(255, 255, 255, 0.3)',
                                borderWidth: 1,
                                callbacks: {
                                    title: function(context) {
                                        return '時刻: ' + context[0].label;
                                    },
                                    label: function(context) {
                                        let label = context.dataset.label || '';
                                        if (label) {
                                            label += ': ';
                                        }
                                        if (context.parsed.y !== null) {
                                            label += context.parsed.y.toFixed(1) + '%';
                                        }
                                        return label;
                                    },
                                    afterBody: function(context) {
                                        if (context.length > 0) {
                                            const dataIndex = context[0].dataIndex;
                                            const hourData = hourlyData.hourly_stats[dataIndex];
                                            if (hourData) {
                                                return 'データ数: ' + (hourData.count || 0) + '件';
                                            }
                                        }
                                        return '';
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                display: true,
                                grid: {
                                    color: 'rgba(0, 0, 0, 0.1)'
                                },
                                title: {
                                    display: true,
                                    text: '時間',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                }
                            },
                            y: {
                                type: 'linear',
                                display: true,
                                position: 'left',
                                title: {
                                    display: true,
                                    text: 'デューティサイクル（%）',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                },
                                grid: {
                                    color: 'rgba(52, 152, 219, 0.2)'
                                }
                            },
                            y1: {
                                type: 'linear',
                                display: true,
                                position: 'right',
                                title: {
                                    display: true,
                                    text: 'エラー率（%）',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                },
                                grid: {
                                    drawOnChartArea: false,
                                    color: 'rgba(255, 99, 132, 0.2)'
                                }
                            }
                        }
                    }
                });
            }

            // 環境要因 時間別パフォーマンス
            const environmentalCtx = document.getElementById('environmentalHourlyChart');
            if (environmentalCtx && hourlyData.hourly_stats) {
                new Chart(environmentalCtx, {
                    type: 'line',
                    data: {
                        labels: hourlyData.hourly_stats.map(d => d.hour + '時'),
                        datasets: [{
                            label: '平均温度（°C）',
                            data: hourlyData.hourly_stats.map(d => d.avg_temperature),
                            borderColor: 'rgb(255, 159, 64)',
                            backgroundColor: 'rgba(255, 159, 64, 0.2)',
                            tension: 0.1,
                            yAxisID: 'y',
                            borderWidth: 3,
                            pointRadius: 4,
                            pointHoverRadius: 6
                        }, {
                            label: '平均日射量（W/m²）',
                            data: hourlyData.hourly_stats.map(d => d.avg_solar_radiation),
                            borderColor: 'rgb(255, 206, 84)',
                            backgroundColor: 'rgba(255, 206, 84, 0.2)',
                            tension: 0.1,
                            yAxisID: 'y1',
                            borderWidth: 2,
                            pointRadius: 3,
                            pointHoverRadius: 5
                        }]
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
                                    usePointStyle: true,
                                    padding: 20,
                                    font: {
                                        size: 12
                                    }
                                }
                            },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                titleColor: 'white',
                                bodyColor: 'white',
                                borderColor: 'rgba(255, 255, 255, 0.3)',
                                borderWidth: 1,
                                callbacks: {
                                    title: function(context) {
                                        return '時刻: ' + context[0].label;
                                    },
                                    label: function(context) {
                                        let label = context.dataset.label || '';
                                        if (label) {
                                            label += ': ';
                                        }
                                        if (context.parsed.y !== null) {
                                            if (context.dataset.yAxisID === 'y1') {
                                                label += context.parsed.y.toFixed(0) + ' W/m²';
                                            } else {
                                                label += context.parsed.y.toFixed(1) + '°C';
                                            }
                                        }
                                        return label;
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                display: true,
                                grid: {
                                    color: 'rgba(0, 0, 0, 0.1)'
                                },
                                title: {
                                    display: true,
                                    text: '時間',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                }
                            },
                            y: {
                                type: 'linear',
                                display: true,
                                position: 'left',
                                title: {
                                    display: true,
                                    text: '温度（°C）',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                },
                                grid: {
                                    color: 'rgba(255, 159, 64, 0.2)'
                                }
                            },
                            y1: {
                                type: 'linear',
                                display: true,
                                position: 'right',
                                title: {
                                    display: true,
                                    text: '日射量（W/m²）',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                },
                                grid: {
                                    drawOnChartArea: false,
                                    color: 'rgba(255, 206, 84, 0.2)'
                                }
                            }
                        }
                    }
                });
            }
        }

        function generateBoxplotCharts() {
            // デューティサイクル 箱ひげ図
            const dutyCycleBoxplotCtx = document.getElementById('dutyCycleBoxplotChart');
            if (dutyCycleBoxplotCtx && hourlyData.hourly_boxplot) {
                const boxplotData = [];
                for (let hour = 0; hour < 24; hour++) {
                    if (hourlyData.hourly_boxplot[hour] && hourlyData.hourly_boxplot[hour].duty_cycle) {
                        boxplotData.push({
                            x: hour + '時',
                            y: hourlyData.hourly_boxplot[hour].duty_cycle
                        });
                    }
                }

                new Chart(dutyCycleBoxplotCtx, {
                    type: 'boxplot',
                    data: {
                        labels: boxplotData.map(d => d.x),
                        datasets: [{
                            label: 'デューティサイクル分布（%）',
                            data: boxplotData.map(d => d.y),
                            backgroundColor: 'rgba(52, 152, 219, 0.6)',
                            borderColor: 'rgb(52, 152, 219)',
                            borderWidth: 2,
                            outlierColor: 'rgb(239, 68, 68)',
                            medianColor: 'rgb(255, 193, 7)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'top'
                            },
                            tooltip: {
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                titleColor: 'white',
                                bodyColor: 'white',
                                callbacks: {
                                    title: function(context) {
                                        return '時刻: ' + context[0].label;
                                    },
                                    label: function(context) {
                                        const stats = context.parsed;
                                        return [
                                            '最小値: ' + stats.min.toFixed(1) + '%',
                                            '第1四分位: ' + stats.q1.toFixed(1) + '%',
                                            '中央値: ' + stats.median.toFixed(1) + '%',
                                            '第3四分位: ' + stats.q3.toFixed(1) + '%',
                                            '最大値: ' + stats.max.toFixed(1) + '%'
                                        ];
                                    },
                                    afterBody: function(context) {
                                        if (context.length > 0) {
                                            const outliers = context[0].parsed.outliers || [];
                                            if (outliers.length > 0) {
                                                return '外れ値: ' + outliers.length + '個';
                                            }
                                        }
                                        return '';
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                display: true,
                                title: {
                                    display: true,
                                    text: '時間',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                }
                            },
                            y: {
                                display: true,
                                title: {
                                    display: true,
                                    text: 'デューティサイクル（%）',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // 温度 箱ひげ図
            const temperatureBoxplotCtx = document.getElementById('temperatureBoxplotChart');
            if (temperatureBoxplotCtx && hourlyData.hourly_boxplot) {
                const boxplotData = [];
                for (let hour = 0; hour < 24; hour++) {
                    if (hourlyData.hourly_boxplot[hour] && hourlyData.hourly_boxplot[hour].temperature) {
                        boxplotData.push({
                            x: hour + '時',
                            y: hourlyData.hourly_boxplot[hour].temperature
                        });
                    }
                }

                new Chart(temperatureBoxplotCtx, {
                    type: 'boxplot',
                    data: {
                        labels: boxplotData.map(d => d.x),
                        datasets: [{
                            label: '温度分布（°C）',
                            data: boxplotData.map(d => d.y),
                            backgroundColor: 'rgba(255, 159, 64, 0.6)',
                            borderColor: 'rgb(255, 159, 64)',
                            borderWidth: 2,
                            outlierColor: 'rgb(239, 68, 68)',
                            medianColor: 'rgb(255, 193, 7)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'top'
                            },
                            tooltip: {
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                titleColor: 'white',
                                bodyColor: 'white',
                                callbacks: {
                                    title: function(context) {
                                        return '時刻: ' + context[0].label;
                                    },
                                    label: function(context) {
                                        const stats = context.parsed;
                                        return [
                                            '最小値: ' + stats.min.toFixed(1) + '°C',
                                            '第1四分位: ' + stats.q1.toFixed(1) + '°C',
                                            '中央値: ' + stats.median.toFixed(1) + '°C',
                                            '第3四分位: ' + stats.q3.toFixed(1) + '°C',
                                            '最大値: ' + stats.max.toFixed(1) + '°C'
                                        ];
                                    },
                                    afterBody: function(context) {
                                        if (context.length > 0) {
                                            const outliers = context[0].parsed.outliers || [];
                                            if (outliers.length > 0) {
                                                return '外れ値: ' + outliers.length + '個';
                                            }
                                        }
                                        return '';
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                display: true,
                                title: {
                                    display: true,
                                    text: '時間',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                }
                            },
                            y: {
                                display: true,
                                title: {
                                    display: true,
                                    text: '温度（°C）',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                }
                            }
                        }
                    }
                });
            }
        }

        function generateCorrelationCharts() {
            // 相関分析のチャートを生成（必要に応じて追加実装）
            // 現在は基本的な情報表示のみでチャートは無し
            console.log('Correlation data loaded:', correlationData);
        }
    """
