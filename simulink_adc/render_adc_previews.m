function render_adc_previews(output_folder)
% Export actual model diagrams, not a hand-drawn surrogate.
model='adc_behavioral';
paths={model,[model '/Stage_1'],[model '/Digital_correction'],[model '/Gu_background_update']};
names={'signal_flow','stage_detail','digital_detail','learning_detail'};
for j=1:numel(paths)
    set_param(paths{j},'ZoomFactor','FitSystem');
    print(['-s' paths{j}],'-dpng','-r130',fullfile(output_folder,[names{j} '.png']));
end
end
