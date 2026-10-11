function render_adc_results(reference_folder,output_folder)
% Offline display only: Python reference outputs never enter the ADC model.
input=readmatrix(fullfile(reference_folder,'demo_tone_input.csv'));
physical=readmatrix(fullfile(output_folder,'demo_tone_physical_trace.csv'));
actual=readmatrix(fullfile(output_folder,'demo_tone_digital_trace.csv'));
expected=readmatrix(fullfile(reference_folder,'demo_tone_digital_trace.csv'));
learning=readmatrix(fullfile(output_folder,'demo_tone_learning_trace.csv'));
figure('Visible','off','Color','white','Position',[100 100 1400 900]);
set(groot,'defaultAxesColor','w','defaultAxesXColor','k','defaultAxesYColor','k', ...
    'defaultTextColor','k','defaultLegendColor','w','defaultLegendTextColor','k');
set(groot,'defaultAxesColorOrder',[.10 .30 .50;.80 .30 .10;.20 .55 .40;.55 .30 .65; ...
    .10 .50 .60;.55 .42 .10;.65 .20 .40;.35 .35 .35]);
layout=tiledlayout(2,2,'TileSpacing','compact','Padding','compact');
nexttile;
plot(input(1:256,1),[input(1:256,2) physical(1:256,11) physical(1:256,20) physical(1:256,30)],'LineWidth',1);
grid on; xlabel('Conversion index'); ylabel('Normalized voltage');
title('Input and intermediate analog signals');
legend('Input','Stage1 main','Stage1 auxiliary','Stage2 main','Location','southoutside');
nexttile;
plot(input(1:128,1),expected(1:128,1),'Color',[.7 .7 .7],'LineWidth',3); hold on;
plot(input(1:128,1),actual(1:128,1),'b.','MarkerSize',7);
plot(input(1:128,1),actual(1:128,2),'--','Color',[.9 .5 .2]);
grid on; xlabel('Conversion index'); ylabel('Output code');
title('Python and Simulink output overlay');
legend('Python calibrated','Simulink calibrated','Uncalibrated','Location','southoutside');
nexttile;
plot(input(:,1),actual(:,1)-expected(:,1),'LineWidth',1);
grid on; xlabel('Conversion index'); ylabel('Simulink - Python (code)');
title(sprintf('All 4096 outputs: maximum difference %.3g',max(abs(actual(:,1)-expected(:,1)))));
nexttile;
plot(input(:,1),learning(:,1:8),'LineWidth',1);
grid on; xlabel('Conversion index'); ylabel('Digital PWL slope');
title('Two banks; coefficients change after each window commit');
legend('k1.1','k1.2','k1.3','k1.4','k2.1','k2.2','k2.3','k2.4','Location','southoutside','NumColumns',4);
heading=title(layout,'Behavioral ADC | same input and dither | 120-conversion point30 candidate');
heading.Color='k';
set(findall(gcf,'Type','text'),'Color','k');
exportgraphics(gcf,fullfile(output_folder,'python_simulink_comparison.png'),'Resolution',150);
close(gcf);
end
