function render_adc_harmonics(run_folder)
% Explicit folded harmonic amplitudes from verified native Simulink output.
folder=fullfile(run_folder,'figures');
p=jsondecode(fileread(fullfile(run_folder,'protocol.json')));
s=jsondecode(fileread(fullfile(run_folder,'summary.json')));
prefix='strong_nonlinearity'; case_label='Gain nonlinearity increased 3x';
if isfield(p.harmonic_analysis,'figure_prefix'), prefix=p.harmonic_analysis.figure_prefix; end
if isfield(p.harmonic_analysis,'case_label'), case_label=p.harmonic_analysis.case_label; end
sp=readmatrix(fullfile(folder,'spectra.csv'));
h=readmatrix(fullfile(folder,'harmonics.csv'));
odd=h(mod(h(:,1),2)==1,:);
blue=[.12 .36 .62]; orange=[.88 .36 .13];
fig=figure('Visible','off','Color','w','Position',[60 60 1500 1040]);
t=tiledlayout(2,2,'TileSpacing','compact','Padding','compact');
for j=1:2
    nexttile; plot(sp(:,1)/1e6,sp(:,j+1),'Color',orange*(j==1)+blue*(j==2),'LineWidth',.5); hold on;
    scatter(odd(:,3)/1e6,odd(:,3+j),30,'k','o','LineWidth',.9);
    xlim([0 p.test.sample_rate_hz/2/1e6]); ylim([-135 0]); grid on;
    xlabel('Folded frequency (MHz)'); ylabel('Magnitude (dBFS)');
    for i=1:size(odd,1)
        text(odd(i,3)/1e6,odd(i,3+j)+3,sprintf('H%d',odd(i,1)), ...
            'FontSize',8,'HorizontalAlignment','center','Color','k');
    end
    if j==1, label='Before: unity banks'; m=s.checkpoints.x0.floating;
    else, label='After: learned banks, frozen'; m=s.checkpoints.(sprintf('x%d',p.training.conversions)).floating; end
    title(sprintf('%s | SNDR %.2f dB | SFDR %.2f dBc',label,m.sndr_db,m.sfdr_dbc));
end
nexttile; hold on;
for i=1:size(odd,1)
    plot(odd(i,6:7),[i i],'-','Color',[.7 .7 .7],'LineWidth',1.2);
end
scatter(odd(:,6),1:size(odd,1),42,orange,'filled');
scatter(odd(:,7),1:size(odd,1),42,blue,'filled');
yticks(1:size(odd,1)); yticklabels(compose('HD%d',odd(:,1))); ylim([.3 size(odd,1)+.7]);
set(gca,'YDir','reverse'); grid on; xlabel('Harmonic level (dBc): more negative means less distortion');
title('Odd harmonics HD3..HD31 | orange: before, blue: after');
nexttile;
order=s.harmonic_analysis.floating.strongest_uncalibrated_odd_order;
chosen=h(h(:,1)==order,:);
index=chosen(2)+1;
radius=p.harmonic_analysis.zoom_radius_bins;
ix=max(2,index-radius):min(size(sp,1),index+radius);
plot(sp(ix,1)/1e6,sp(ix,2),'o-','Color',orange,'MarkerSize',3); hold on;
plot(sp(ix,1)/1e6,sp(ix,3),'s-','Color',blue,'MarkerSize',3);
xline(chosen(3)/1e6,':','Color',[.3 .3 .3]); grid on;
xlabel('Folded frequency (MHz)'); ylabel('Magnitude (dBFS)');
legend('Before','After','Location','southoutside','NumColumns',2);
title(sprintf('HD%d: %.2f to %.2f dBFS | suppression %.2f dB', ...
    order,chosen(4),chosen(5),chosen(8)));
title(t,sprintf('%s | %.6f MHz tone | %d training conversions',case_label, ...
    p.test.sample_rate_hz*p.test.fundamental_bin/p.test.samples/1e6,p.training.conversions), ...
    'Color','k','FontSize',14);
subtitle(t,'Harmonic bin b=min(mod(h*k,N),N-mod(h*k,N)); all HD2..HD31 retained; zoom uses largest BEFORE odd harmonic', ...
    'Color',[.2 .2 .2],'FontSize',10);
save_figure(fig,folder,[prefix '_harmonics']);

fig=figure('Visible','off','Color','w','Position',[60 60 1400 780]);
t=tiledlayout(2,2,'TileSpacing','compact','Padding','compact');
z=linspace(-.625,.625,1001);
for stage=1:2
    current=p.(sprintf('stage%d_truth',stage));
    previous=p.harmonic_analysis.(sprintf('previous_stage%d_truth',stage));
    nexttile; plot(z,previous(2)*z.^3,'--','Color',blue,'LineWidth',1.5); hold on;
    plot(z,current(2)*z.^3,'Color',orange,'LineWidth',1.5);
    grid on; xlabel('Nominal residue z'); ylabel('g(z) - a*z');
    title(sprintf('Stage %d: nonlinear departure from its linear gain',stage));
    legend('Previous cubic','Current cubic','Location','northwest');
end
for stage=1:2
    current=p.(sprintf('stage%d_truth',stage));
    previous=p.harmonic_analysis.(sprintf('previous_stage%d_truth',stage));
    nexttile; plot(z,previous(1)+3*previous(2)*z.^2,'--','Color',blue,'LineWidth',1.5); hold on;
    plot(z,current(1)+3*current(2)*z.^2,'Color',orange,'LineWidth',1.5);
    grid on; xlabel('Nominal residue z'); ylabel('dg/dz');
    title(sprintf('Stage %d: gain compression and positive derivative',stage));
end
title(t,'Physical gain nonlinearity used in this run: g(z)=a*z+b*z^3','Color','k','FontSize',14);
subtitle(t,[case_label '; synthetic physical truth is never supplied to the digital learner'], ...
    'Color',[.2 .2 .2],'FontSize',10);
save_figure(fig,folder,[prefix '_transfer']);
fprintf('Harmonic comparison and nonlinear transfer figures exported as PNG and SVG.\n');
end

function save_figure(fig,folder,name)
set(findall(fig,'Type','text'),'Color','k');
exportgraphics(fig,fullfile(folder,[name '.png']),'Resolution',180);
exportgraphics(fig,fullfile(folder,[name '.svg']),'ContentType','vector');
close(fig);
end
