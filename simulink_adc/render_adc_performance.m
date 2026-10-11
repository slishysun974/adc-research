function render_adc_performance(run_folder)
% Offline scientific figures from native Simulink traces and verified metrics.
folder=fullfile(run_folder,'figures');
summary=jsondecode(fileread(fullfile(run_folder,'summary.json')));
p=jsondecode(fileread(fullfile(run_folder,'protocol.json')));
spectra=readmatrix(fullfile(folder,'spectra.csv'));
learning=readmatrix(fullfile(folder,'coefficient_windows.csv'));
checkpoints=readmatrix(fullfile(folder,'checkpoint_metrics.csv'));
signals=readmatrix(fullfile(folder,'signal_trace.csv'));
set(groot,'defaultAxesFontName','Arial','defaultAxesFontSize',11, ...
    'defaultAxesColor','w','defaultAxesXColor','k','defaultAxesYColor','k', ...
    'defaultTextColor','k','defaultLegendColor','w','defaultLegendTextColor','k');
colors=[.12 .36 .62;.88 .36 .13;.19 .57 .40;.55 .33 .68];
set(groot,'defaultAxesColorOrder',colors);
before=summary.checkpoints.x0.floating;
after=summary.checkpoints.(sprintf('x%d',p.training.conversions)).floating;
% MATLAB jsondecode can prefix digit-leading field names with x.
fig=figure('Visible','off','Color','w','Position',[50 50 1400 840]);
t=tiledlayout(2,2,'TileSpacing','compact','Padding','compact');
for j=1:2
    nexttile; plot(spectra(:,1)/1e6,spectra(:,j+1),'Color',colors(j,:),'LineWidth',.6);
    xlim([0 1500]); ylim([-130 0]); grid on; xlabel('Frequency (MHz)'); ylabel('Magnitude (dBFS)');
    if j==1, m=before; label='Before: unity banks'; else, m=after; label='After: learned banks, frozen'; end
    title(sprintf('%s | SNDR %.2f dB | SFDR %.2f dBc',label,m.sndr_db,m.sfdr_dbc));
end
nexttile;
bar([before.sndr_db after.sndr_db;before.sfdr_dbc after.sfdr_dbc]);
xticklabels({'SNDR (dB)','SFDR (dBc)'}); ylabel('Performance'); grid on; ylim([0 85]);
legend('Before','After','Location','northwest'); title('Same input and dither; native floating output');
nexttile; plot(checkpoints(:,1)/1e6,checkpoints(:,2),'-o','LineWidth',1.8); hold on;
plot(checkpoints(:,1)/1e6,checkpoints(:,5),'--s','LineWidth',1.4);
if ~isfield(p,'harmonic_analysis')
    yline(60.3,':','Paper Fig.21: 60.3 dB','Color',[.3 .3 .3],'LabelHorizontalAlignment','right');
end
grid on; xlabel('Training conversions (million)'); ylabel('SNDR (dB)');
legend('Model float','Offline 12-bit rounding','Location','southeast');
title('Checkpoint tests with adaptation disabled');
title(t,sprintf('3 GS/s behavioral ADC | %.6f GHz tone | %.3f dBFS | %d training conversions', ...
    p.test.sample_rate_hz*p.test.fundamental_bin/p.test.samples/1e9,20*log10(p.test.amplitude),p.training.conversions), ...
    'Color','k','FontSize',14);
subtitle(t,'Fig.21 / Fig.24 style comparison; synthetic static transfer and full120 update differ from chip conditions', ...
    'Color',[.2 .2 .2],'FontSize',10);
save_figure(fig,folder,'performance_overview');

fig=figure('Visible','off','Color','w','Position',[50 50 1400 860]);
t=tiledlayout(3,1,'TileSpacing','compact','Padding','compact');
for s=1:2
    nexttile; plot(learning(:,1)/1e6,learning(:,(s-1)*4+(2:5)),'LineWidth',1.1);
    grid on; ylabel('PWL slope'); title(sprintf('Stage %d: independently learned four-slope bank',s));
    legend('k1','k2','k3','k4','Location','eastoutside');
end
nexttile; plot(checkpoints(:,1)/1e6,checkpoints(:,2),'-o','LineWidth',1.5); hold on;
plot(checkpoints(:,1)/1e6,checkpoints(:,3),'-s','LineWidth',1.5);
grid on; xlabel('Actual training conversions (million)'); ylabel('dB / dBc');
legend('Frozen-test SNDR','Frozen-test SFDR','Location','eastoutside');
title('Performance is sampled at fixed checkpoints; coefficient traces include every commit');
title(t,'Fig.24 style: coefficient evolution and independent coherent-tone evaluation','Color','k','FontSize',14);
subtitle(t,'All 120 observations per window are used; upper slopes can remain unsupported; no steady-state claim', ...
    'Color',[.2 .2 .2],'FontSize',10);
save_figure(fig,folder,'coefficient_evolution');

fig=figure('Visible','off','Color','w','Position',[50 50 1400 920]);
t=tiledlayout(2,2,'TileSpacing','compact','Padding','compact');
ix=1:48;
nexttile; plot(signals(ix,1),signals(ix,2:5),'-o','MarkerSize',3); grid on;
xlabel('Conversion index'); ylabel('Normalized voltage'); title('Input, main residue and auxiliary residue');
legend('Input','Stage1 main','Stage1 auxiliary','Stage2 main','Location','southoutside','NumColumns',2);
nexttile; plot(signals(ix,1),signals(ix,8),'Color',[.65 .65 .65],'LineWidth',3); hold on;
plot(signals(ix,1),signals(ix,7),'b.','MarkerSize',9); plot(signals(ix,1),signals(ix,6),'--','Color',colors(2,:));
grid on; xlabel('Conversion index'); ylabel('Output code'); title('Native corrected output and raw reconstruction');
legend('Ideal (offline)','Corrected','Raw','Location','southoutside','NumColumns',3);
nexttile; plot(signals(1:192,1),signals(1:192,6)-signals(1:192,8),'Color',colors(2,:)); hold on;
plot(signals(1:192,1),signals(1:192,7)-signals(1:192,8),'Color',colors(1,:));
grid on; xlabel('Conversion index'); ylabel('Code error'); title('Error relative to ideal code (offline scoring only)');
legend('Before','After','Location','southoutside');
nexttile; plot(signals(:,1),signals(:,10)); grid on; ylim([-1 1]);
xlabel('Conversion index'); ylabel('Simulink - Python (code)');
title(sprintf('Independent implementation parity | maximum difference %.3g',max(abs(signals(:,10)))));
title(t,'Signal flow and numerical correctness | final frozen checkpoint','Color','k','FontSize',14);
subtitle(t,sprintf('All %.0f scalar trace comparisons passed; overall maximum error %.3g', ...
    summary.scalar_comparisons,summary.max_trace_error),'Color',[.2 .2 .2],'FontSize',10);
save_figure(fig,folder,'signals_and_parity');
fprintf('Three scientific figures exported as PNG and SVG.\n');
if isfield(p,'harmonic_analysis'), render_adc_harmonics(run_folder); end
end

function save_figure(fig,folder,name)
set(findall(fig,'Type','text'),'Color','k');
exportgraphics(fig,fullfile(folder,[name '.png']),'Resolution',180);
exportgraphics(fig,fullfile(folder,[name '.svg']),'ContentType','vector');
close(fig);
end
