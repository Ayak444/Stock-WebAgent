import React, { useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

interface ChartProps {
  data: any[];
}

export const Chart: React.FC<ChartProps> = ({ data }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Initialize Chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8B95A5',
      },
      grid: {
        vertLines: { color: 'rgba(42, 46, 57, 0.5)' },
        horzLines: { color: 'rgba(42, 46, 57, 0.5)' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 450,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#00F2FE',
      downColor: '#FF2A55',
      borderVisible: false,
      wickUpColor: '#00F2FE',
      wickDownColor: '#FF2A55',
    });
    
    seriesRef.current = candlestickSeries;

    // Format Data safely
    if (data && data.length > 0) {
      try {
        const formattedData = data.map(item => ({
          time: String(item.date).split('T')[0],
          open: Number(item.open),
          high: Number(item.high),
          low: Number(item.low),
          close: Number(item.close),
        }))
        // Ensure strictly ascending order and unique dates to prevent crash
        .sort((a, b) => a.time.localeCompare(b.time))
        .filter((item, index, arr) => index === 0 || item.time !== arr[index - 1].time);

        candlestickSeries.setData(formattedData);
      } catch (err) {
        console.error("Chart Render Error:", err);
      }
    }

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data]);

  return (
    <div 
      ref={chartContainerRef} 
      style={{ width: '100%', height: '450px', position: 'relative' }} 
    />
  );
};
