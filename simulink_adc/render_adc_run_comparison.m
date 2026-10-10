function render_adc_run_comparison(run_folder, previous_folder)
% Offline visual comparison of two complete, independently verified runs.
% Both physical nonlinearity and learning rates changed; do not attribute
% between-run differences to either factor alone.
p=jsondecode(fileread(fullfile(run_folder,'protocol.json')));
old=jsondecode(fileread(fullfile(previous_folder,'protocol.json')));
assert(p.test.samples==old.test.samples && p.test.fundamental_bin==old.test.fundamental_bin);
assert(p.test.sample_rate_hz==old.test.sample_rate_hz && p.test.amplitude==old.test.amplitude);
assert(p.training.input_seed==old.training.input_seed && p.training.dither_seed==old.training.dither_seed);
assert(p.test.dither_seed==old.test.dither_seed);
for folder={run_folder,previous_folder}
    v=jsondecode(fileread(fullfile(folder{1},'verification.json')));
    assert(v.all_fields_passed);
end
folder=fullfile(run_folder,'figures');
now=readmatrix(fullfile(folder,'checkpoint_metrics.csv'));
before=readmatrix(fullfile(previous_folder,'figures','checkpoint_metrics.csv'));
assert(isequal(now(:,1),before(:,1)));
learning=readmatrix(fullfile(folder,'coefficient_windows.csv'));
prior=readmatrix(fullfile(previous_folder,'figures','coefficient_windows.csv'));
assert(isequal(learning(:,1),prior(:,1)));
h=readmatrix(fullfile(folder,'harmonics.csv'));
hp=readmatrix(fullfile(previous_folder,'figures','harmonics.csv'));
assert(isequal(h(:,1:3),hp(:,1:3)));
blue=[.12 .36 .62]; orange=[.88 .36 .13];
fig=figure('Visible','off','Color','w','Position',[60 60 1500 980]);
t=tiledlayout(2,2,'TileSpacing','compact','Padding','compact');
nexttile; plot(before(:,1)/1e6,before(:,2),'-o','Color',orange,'LineWidth',1.5); hold on;
plot(now(:,1)/1e6,now(:,2),'-s','Color',blue,'LineWidth',1.5); grid on;
xlabel('Training conversions (million)'); ylabel('Frozen-test SNDR (dB)');
title('All seven predetermined checkpoints');
legend('Previous: stronger cubic, original rate','Current: cubic /2, rate /4','Location','best');
for stage=1:2
    nexttile; hold on;
    plot(prior(:,1)/1e6,prior(:,(stage-1)*4+2),'-','Color',orange,'LineWidth',.8);
    plot(learning(:,1)/1e6,learning(:,(stage-1)*4+2),'-','Color',blue,'LineWidth',.8);
    plot(prior(:,1)/1e6,prior(:,(stage-1)*4+3),'--','Color',orange,'LineWidth',.8);
    plot(learning(:,1)/1e6,learning(:,(stage-1)*4+3),'--','Color',blue,'LineWidth',.8);
    grid on; xlabel('Training conversions (million)'); ylabel('PWL slope');
    title(sprintf('Stage %d: every commit; upper slopes remain unsupported',stage));
    legend('Previous k1','Current k1','Previous k2','Current k2','Location','best');
end
nexttile; odd=mod(h(:,1),2)==1;
plot(h(odd,1),hp(odd,7),'-o','Color',orange,'LineWidth',1.4); hold on;
plot(h(odd,1),h(odd,7),'-s','Color',blue,'LineWidth',1.4); grid on;
xticks(h(odd,1)); xlabel('Odd harmonic order'); ylabel('Final harmonic level (dBc)');
title('Predetermined final banks: lower level means less distortion');
legend('Previous final output','Current final output','Location','best');
title(t,'Previous and current runs: cubic terms /2 and learning rates /4','Color','k','FontSize',14);
subtitle(t,'Identical inputs, dither, test frequency and horizon; both factors changed, so this is not a learning-rate-only comparison', ...
    'Color',[.2 .2 .2],'FontSize',10);
set(findall(fig,'Type','text'),'Color','k');
exportgraphics(fig,fullfile(folder,'reduced_vs_strong.png'),'Resolution',180);
exportgraphics(fig,fullfile(folder,'reduced_vs_strong.svg'),'ContentType','vector');
close(fig);
fprintf('Previous/current comparison exported from verified records.\n');
end
