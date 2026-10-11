function open_adc_demo()
% Open the model and scopes with its embedded default input/parameters.
folder=fileparts(mfilename('fullpath'));
addpath(folder);
open_system(fullfile(folder,'adc_behavioral.slx'));
set_param('adc_behavioral','ZoomFactor','FitSystem');
open_system('adc_behavioral/Residue_scope');
open_system('adc_behavioral/Code_scope');
open_system('adc_behavioral/Coefficient_scope');
sim('adc_behavioral');
end
