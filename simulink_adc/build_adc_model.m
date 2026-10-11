function model_file = build_adc_model(reference_folder)
% Build a genuine, editable block diagram. No Python call in the signal path.
folder=fileparts(mfilename('fullpath'));
if nargin == 0
    reference_folder=fullfile(folder,'outputs','reference');
    Simulink.fileGenControl('set','CacheFolder',fullfile(folder,'outputs','cache'), ...
        'CodeGenFolder',fullfile(folder,'outputs','codegen'),'createDir',true);
end
manifest=jsondecode(fileread(fullfile(reference_folder,'manifest.json')));
demo=manifest.cases(strcmp({manifest.cases.name},'demo_tone'));
model='adc_behavioral';
if bdIsLoaded(model), close_system(model,0); end
load_system('simulink');
new_system(model);
set_param(model,'Solver','FixedStepDiscrete','FixedStep','1', ...
    'StartTime','0','StopTime','4095','SimulationMode','normal', ...
    'ReturnWorkspaceOutputs','on','SignalLogging','on','BlockReduction','off', ...
    'SaveTime','on','SaveOutput','off','Description', ...
    'Gu behavioral ADC: independent Simulink implementation, one tick per conversion.');
adc_load_case(model,reference_folder,demo);

% Stimulus is shared; reference outputs are never loaded into this model.
source(model,'Input_x','x_signal',[25 115 120 145]);
source(model,'Dither_1','d1_signal',[25 225 120 255]);
source(model,'Dither_2','d2_signal',[25 345 120 375]);
source(model,'Sample_index','n_signal',[25 475 120 505]);
b(model,'simulink/Math Operations/Gain','Flash1_aux_gain',[160 60 225 95],'Gain','C.aux1_gain');
b(model,'simulink/Math Operations/Bias','Flash1_aux_offset',[250 60 320 95],'Bias','C.aux1_offset');
wire(model,'Input_x/1','Flash1_aux_gain/1','x');
wire(model,'Flash1_aux_gain/1','Flash1_aux_offset/1','aux1_scaled');
make_stage([model '/Stage_1'],1,[365 105 520 290],folder);
wire(model,'Input_x/1','Stage_1/1','main_input');
wire(model,'Flash1_aux_offset/1','Stage_1/2','flash1_input');
wire(model,'Dither_1/1','Stage_1/3','d1_tag');

make_auxiliary([model '/Auxiliary_path'],[575 40 735 105],folder);
wire(model,'Stage_1/3','Auxiliary_path/1','preamp1');
wire(model,'Stage_1/1','Auxiliary_path/2','main_residue1');
make_stage([model '/Stage_2'],2,[790 105 945 290],folder);
wire(model,'Stage_1/1','Stage_2/1','main_to_cdac2');
wire(model,'Auxiliary_path/1','Stage_2/2','aux_to_flash2');
wire(model,'Dither_2/1','Stage_2/3','d2_tag');
fn(model,'SAR_8bit',[1010 125 1120 230],'adc_sar',folder);
wire(model,'Stage_2/1','SAR_8bit/1','residue2');
wire(model,'Sample_index/1','SAR_8bit/2','conversion_index');

make_digital([model '/Digital_correction'],[1180 100 1370 355],folder);
make_learning([model '/Gu_background_update'],[800 405 1030 555],folder);
for pair={'Stage_1/2','Digital_correction/1';'Stage_2/2','Digital_correction/2'; ...
        'SAR_8bit/2','Digital_correction/3';'Dither_1/1','Digital_correction/4'; ...
        'Dither_2/1','Digital_correction/5';'Gu_background_update/1','Digital_correction/6'; ...
        'Gu_background_update/2','Digital_correction/7';'Digital_correction/5','Gu_background_update/1'; ...
        'Digital_correction/6','Gu_background_update/2';'Digital_correction/7','Gu_background_update/3'; ...
        'Digital_correction/8','Gu_background_update/4';'Sample_index/1','Gu_background_update/5'}'
    wire(model,pair{1},pair{2},'');
end
b(model,'simulink/Sinks/Scope','Residue_scope',[580 180 645 235],'NumInputPorts','3');
wire(model,'Stage_1/1','Residue_scope/1','');
wire(model,'Auxiliary_path/1','Residue_scope/2','');
wire(model,'Stage_2/1','Residue_scope/3','');
b(model,'simulink/Sinks/Scope','Code_scope',[1430 105 1495 175],'NumInputPorts','2');
wire(model,'Digital_correction/1','Code_scope/1','corrected_output');
wire(model,'Digital_correction/2','Code_scope/2','uncalibrated_output');
b(model,'simulink/Sinks/Scope','Coefficient_scope',[1105 470 1170 535],'NumInputPorts','2');
wire(model,'Gu_background_update/1','Coefficient_scope/1','k1_old');
wire(model,'Gu_background_update/2','Coefficient_scope/2','k2_old');
fn(model,'Overload_and_clipping',[1190 620 1370 750],'adc_flags',folder);
for pair={'Input_x/1','Overload_and_clipping/1';'Flash1_aux_offset/1','Overload_and_clipping/2'; ...
        'Stage_1/1','Overload_and_clipping/3';'Auxiliary_path/1','Overload_and_clipping/4'; ...
        'Stage_2/1','Overload_and_clipping/5';'Digital_correction/4','Overload_and_clipping/6'; ...
        'Digital_correction/3','Overload_and_clipping/7'}'
    wire(model,pair{1},pair{2},'');
end
% These groups have documented scalar ordering in manifest.json.
physical={'Stage_1/4','Stage_2/4', ...
    'Auxiliary_path/2','Auxiliary_path/3','SAR_8bit/1','SAR_8bit/2','SAR_8bit/3','SAR_8bit/4','Overload_and_clipping/1'};
collect(model,'physical_trace',physical,[1520 450 1560 780]);
collect(model,'digital_trace',{'Digital_correction/9'},[1520 220 1560 260]);
collect(model,'learning_trace',{'Gu_background_update/5'},[1200 480 1240 520]);
collect(model,'stimulus_trace',{'Sample_index/1','Input_x/1','Dither_1/1','Dither_2/1'},[200 600 240 690]);
note=Simulink.Annotation(model, ...
    sprintf('ADC behavioral model | one tick = one conversion\nDouble-click each subsystem for the signal flow.\nBlue: analog candidate. Green: digital-only correction. Orange: feedback.\nScopes: residues, codes, coefficients. Python outputs are offline only.'));
note.Position=[25 780 700 850];
set_param([model '/Stage_1'],'BackgroundColor','[0.84 0.92 0.98]');
set_param([model '/Stage_2'],'BackgroundColor','[0.84 0.92 0.98]');
set_param([model '/Auxiliary_path'],'BackgroundColor','[0.84 0.92 0.98]');
set_param([model '/Digital_correction'],'BackgroundColor','[0.87 0.95 0.88]');
set_param([model '/Gu_background_update'],'BackgroundColor','[0.99 0.91 0.79]');
decorate([model '/Stage_1'],'Stage 1\nFlash / CDAC\nResidue amplifier');
decorate([model '/Stage_2'],'Stage 2\nFlash / CDAC\nResidue amplifier');
decorate([model '/Auxiliary_path'],'Auxiliary\npath');
decorate([model '/Digital_correction'],'Digital\nPWL correction');
decorate([model '/Gu_background_update'],'Gu gated-LMS\nWindow commit');
set_param(model,'Location',[30 50 1530 920]);
set_param(model,'ZoomFactor','FitSystem');
set_param(model,'SimulationCommand','update');
model_file=fullfile(folder,[model '.slx']);
save_system(model,model_file);
fprintf('Saved editable model: %s\n',model_file);
end

function make_stage(path,index,position,folder)
subsystem(path,position);
ports(path,{'main','auxiliary','dither_tag'}, ...
    {'residue','symbol','preamp','trace'});
prefix=sprintf('C.s%d_',index);
fn(path,'Flash',[150 50 260 115],'adc_flash',folder);
constant(path,'Thresholds',[10 20 105 40],[prefix 'thresholds']);
wire(path,'auxiliary/1','Flash/1','auxiliary_voltage');
wire(path,'Thresholds/1','Flash/2','');
fn(path,'CDAC',[330 60 455 180],'adc_cdac',folder);
constant(path,'Levels',[160 190 255 215],[prefix 'levels']);
constant(path,'Mismatch',[160 235 255 260],[prefix 'errors']);
constant(path,'Dither_amplitude',[160 280 255 305],'C.dither_amplitude');
wire(path,'Flash/1','CDAC/1','q');
wire(path,'dither_tag/1','CDAC/2','');
wire(path,'Levels/1','CDAC/3','');
wire(path,'Mismatch/1','CDAC/4','');
wire(path,'Dither_amplitude/1','CDAC/5','');
b(path,'simulink/Math Operations/Sum','Residue_sum',[510 65 535 125],'Inputs','+-+');
wire(path,'main/1','Residue_sum/1','main_voltage');
wire(path,'CDAC/3','Residue_sum/2','actual_cdac');
wire(path,'CDAC/4','Residue_sum/3','injected_dither');
b(path,'simulink/Math Operations/Gain','Actual_gain',[575 65 650 115],'Gain',[prefix 'gain']);
wire(path,'Residue_sum/1','Actual_gain/1','preamp_residue');
fn(path,'Analog_transfer',[690 55 815 125],'adc_analog',folder);
constant(path,'Analog_parameters',[545 175 655 200],[prefix 'analog']);
wire(path,'Actual_gain/1','Analog_transfer/1','linear_target');
wire(path,'Analog_parameters/1','Analog_transfer/2','');
fn(path,'Finite_establishment',[875 50 1010 130],'adc_settle',folder);
b(path,'simulink/Discrete/Unit Delay','Previous_residue',[885 220 955 265], ...
    'SampleTime','1','InitialCondition',sprintf('C.initial_analog(%d)',2*index-1));
constant(path,'Phase_parameters',[705 175 810 200],[prefix 'phase']);
wire(path,'Analog_transfer/1','Finite_establishment/1','static_target');
wire(path,'Previous_residue/1','Finite_establishment/2','previous_residue');
wire(path,'Phase_parameters/1','Finite_establishment/3','');
wire(path,'Finite_establishment/1','Previous_residue/1','');
connections={'Finite_establishment/1','residue/1';'Flash/1','symbol/1';'Residue_sum/1','preamp/1'};
for j=1:size(connections,1), wire(path,connections{j,1},connections{j,2},''); end
signals={'auxiliary/1','Flash/1','Flash/2','CDAC/1','CDAC/2','CDAC/3','CDAC/4', ...
    'Residue_sum/1','Analog_transfer/1','Finite_establishment/2','Finite_establishment/1','Flash/3'};
pack(path,'Diagnostic_trace',signals,[1050 300 1080 600],'trace/1');
end

function make_auxiliary(path,position,folder)
subsystem(path,position);
ports(path,{'preamp','main'},{'auxiliary','target','tracking_start'});
fn(path,'Independent_auxiliary',[220 60 390 155],'adc_auxiliary',folder);
constant(path,'Auxiliary_parameters',[60 240 195 270],'C.aux_parameters');
b(path,'simulink/Discrete/Unit Delay','Previous_auxiliary',[240 220 320 255], ...
    'SampleTime','1','InitialCondition','C.initial_analog(2)');
wire(path,'preamp/1','Independent_auxiliary/1','');
wire(path,'main/1','Independent_auxiliary/2','');
wire(path,'Previous_auxiliary/1','Independent_auxiliary/3','');
wire(path,'Auxiliary_parameters/1','Independent_auxiliary/4','');
wire(path,'Independent_auxiliary/1','Previous_auxiliary/1','');
for j=1:3
    names={'auxiliary','target','tracking_start'};
    wire(path,sprintf('Independent_auxiliary/%d',j),[names{j} '/1'],'');
end
end

function make_digital(path,position,folder)
subsystem(path,position);
ports(path,{'q1','q2','backend_centered','d1_tag','d2_tag','k1','k2'}, ...
    {'output','uncalibrated_output','unclipped','uncalibrated_unclipped', ...
     'local1','local2','D1','D2','trace'});
b(path,'simulink/Math Operations/Gain','Dither_copy_1',[150 250 230 280],'Gain','C.copy1');
b(path,'simulink/Math Operations/Gain','Dither_copy_2',[150 300 230 330],'Gain','C.copy2');
b(path,'simulink/Math Operations/Gain','Coarse_1',[650 25 730 55],'Gain','512');
b(path,'simulink/Math Operations/Gain','Coarse_2',[150 100 230 130],'Gain','128');
wire(path,'d1_tag/1','Dither_copy_1/1','');
wire(path,'d2_tag/1','Dither_copy_2/1','');
wire(path,'q1/1','Coarse_1/1','');
wire(path,'q2/1','Coarse_2/1','');
fn(path,'PWL_stage_2',[260 155 385 240],'adc_pwl',folder);
fn(path,'PWL_stage_1',[510 155 635 240],'adc_pwl',folder);
constant(path,'Width_2',[135 400 215 430],'32');
constant(path,'Width_1',[385 400 465 430],'128');
constant(path,'PWL_enabled',[270 440 365 470],'double(C.digital_mode > 0)');
wire(path,'backend_centered/1','PWL_stage_2/1','raw_backend');
wire(path,'k2/1','PWL_stage_2/2','');
wire(path,'Width_2/1','PWL_stage_2/3','');
wire(path,'PWL_enabled/1','PWL_stage_2/4','');
b(path,'simulink/Math Operations/Sum','Raw_stage_1',[440 95 465 160],'Inputs','++-');
wire(path,'Coarse_2/1','Raw_stage_1/1','');
wire(path,'PWL_stage_2/1','Raw_stage_1/2','pwl2_before_dither');
wire(path,'Dither_copy_2/1','Raw_stage_1/3','');
wire(path,'Raw_stage_1/1','PWL_stage_1/1','raw1_after_dither2');
wire(path,'k1/1','PWL_stage_1/2','');
wire(path,'Width_1/1','PWL_stage_1/3','');
wire(path,'PWL_enabled/1','PWL_stage_1/4','');
b(path,'simulink/Math Operations/Sum','Local_learning_1',[670 155 700 200],'Inputs','+-');
b(path,'simulink/Math Operations/Sum','Local_learning_2',[440 265 470 310],'Inputs','+-');
wire(path,'PWL_stage_1/1','Local_learning_1/1','');
wire(path,'Dither_copy_1/1','Local_learning_1/2','');
wire(path,'PWL_stage_2/1','Local_learning_2/1','');
wire(path,'Dither_copy_2/1','Local_learning_2/2','');
b(path,'simulink/Math Operations/Sum','Centered_corrected',[775 75 805 130],'Inputs','++-');
wire(path,'Coarse_1/1','Centered_corrected/1','');
wire(path,'PWL_stage_1/1','Centered_corrected/2','');
wire(path,'Dither_copy_1/1','Centered_corrected/3','');
b(path,'simulink/Math Operations/Bias','Offset_binary',[835 80 915 120],'Bias','2048');
wire(path,'Centered_corrected/1','Offset_binary/1','');
b(path,'simulink/Discontinuities/Saturation','Output_clip',[955 80 1040 120], ...
    'UpperLimit','4095','LowerLimit','0');
wire(path,'Offset_binary/1','Output_clip/1','');
% Raw reconstruction preserves Python sum((512*q1,128*q2))+c3-D1-D2.
b(path,'simulink/Math Operations/Sum','Raw_coarse_sum',[600 525 630 570],'Inputs','++');
wire(path,'Coarse_1/1','Raw_coarse_sum/1',''); wire(path,'Coarse_2/1','Raw_coarse_sum/2','');
b(path,'simulink/Math Operations/Sum','Raw_centered',[670 525 700 570],'Inputs','++');
wire(path,'Raw_coarse_sum/1','Raw_centered/1',''); wire(path,'backend_centered/1','Raw_centered/2','');
b(path,'simulink/Math Operations/Sum','Dither_total',[600 615 630 660],'Inputs','++');
wire(path,'Dither_copy_1/1','Dither_total/1',''); wire(path,'Dither_copy_2/1','Dither_total/2','');
b(path,'simulink/Math Operations/Sum','Raw_dither_subtract',[750 525 780 570],'Inputs','+-');
wire(path,'Raw_centered/1','Raw_dither_subtract/1',''); wire(path,'Dither_total/1','Raw_dither_subtract/2','');
b(path,'simulink/Math Operations/Bias','Raw_offset_binary',[835 525 915 570],'Bias','2048');
wire(path,'Raw_dither_subtract/1','Raw_offset_binary/1','');
b(path,'simulink/Discontinuities/Saturation','Raw_clip',[955 525 1040 570],'UpperLimit','4095','LowerLimit','0');
wire(path,'Raw_offset_binary/1','Raw_clip/1','');
connections={'Output_clip/1','output/1';'Raw_clip/1','uncalibrated_output/1'; ...
    'Offset_binary/1','unclipped/1';'Raw_offset_binary/1','uncalibrated_unclipped/1'; ...
    'Local_learning_1/1','local1/1';'Local_learning_2/1','local2/1'; ...
    'Dither_copy_1/1','D1/1';'Dither_copy_2/1','D2/1'};
for j=1:size(connections,1), wire(path,connections{j,1},connections{j,2},''); end
signals={'Output_clip/1','Raw_clip/1','Offset_binary/1','Raw_offset_binary/1', ...
    'Raw_stage_1/1','PWL_stage_1/1','PWL_stage_2/1','Local_learning_1/1', ...
    'Local_learning_2/1','PWL_stage_1/2','PWL_stage_2/2','Dither_copy_1/1','Dither_copy_2/1'};
pack(path,'Diagnostic_trace',signals,[1070 440 1095 750],'trace/1');
end

function make_learning(path,position,folder)
subsystem(path,position);
ports(path,{'local1','local2','D1','D2','index'},{'k1','k2','next1','next2','trace'});
b(path,'simulink/Discrete/Unit Delay','Coefficient_bank_1',[180 40 285 90], ...
    'SampleTime','1','InitialCondition','C.initial1');
b(path,'simulink/Discrete/Unit Delay','Coefficient_bank_2',[180 130 285 180], ...
    'SampleTime','1','InitialCondition','C.initial2');
fn(path,'Gates_1',[360 35 485 140],'adc_gate',folder);
fn(path,'Gates_2',[360 200 485 305],'adc_gate',folder);
constant(path,'Width1',[195 260 275 290],'128');
constant(path,'Width2',[195 315 275 345],'32');
wire(path,'Coefficient_bank_1/1','Gates_1/1','');
wire(path,'Coefficient_bank_2/1','Gates_2/1','');
wire(path,'Width1/1','Gates_1/2',''); wire(path,'Width2/1','Gates_2/2','');
wire(path,'D1/1','Gates_1/3',''); wire(path,'D2/1','Gates_2/3','');
wire(path,'local1/1','Gates_1/4',''); wire(path,'local2/1','Gates_2/4','');
fn(path,'Window_accumulate_commit',[600 45 825 350],'adc_update',folder);
constant(path,'Mode',[380 385 470 410],'C.digital_mode');
constant(path,'Mu1',[380 435 470 460],'C.mu1');
constant(path,'Mu2',[380 485 470 510],'C.mu2');
signals={'Coefficient_bank_1/1','Coefficient_bank_2/1','Gates_1/2','Gates_2/2', ...
    'Gates_1/3','Gates_2/3','D1/1','D2/1','local1/1','local2/1','index/1','Mode/1','Mu1/1','Mu2/1'};
for j=1:numel(signals), wire(path,signals{j},sprintf('Window_accumulate_commit/%d',j),''); end
wire(path,'Window_accumulate_commit/1','Coefficient_bank_1/1','commit_for_next_conversion1');
wire(path,'Window_accumulate_commit/2','Coefficient_bank_2/1','commit_for_next_conversion2');
wire(path,'Coefficient_bank_1/1','k1/1',''); wire(path,'Coefficient_bank_2/1','k2/1','');
wire(path,'Window_accumulate_commit/1','next1/1',''); wire(path,'Window_accumulate_commit/2','next2/1','');
signals={'Coefficient_bank_1/1','Coefficient_bank_2/1','Window_accumulate_commit/1', ...
    'Window_accumulate_commit/2','Gates_1/1','Gates_2/1','Gates_1/2','Gates_2/2', ...
    'Gates_1/3','Gates_2/3','Window_accumulate_commit/3','Window_accumulate_commit/4', ...
    'Window_accumulate_commit/5','Window_accumulate_commit/6','Window_accumulate_commit/7'};
b(path,'simulink/Signal Routing/Mux','Trace_pack',[870 390 895 700],'Inputs',num2str(numel(signals)));
for j=1:numel(signals), wire(path,signals{j},sprintf('Trace_pack/%d',j),''); end
wire(path,'Trace_pack/1','trace/1','');
end

function subsystem(path,position)
add_block('built-in/Subsystem',path,'Position',position);
end
function ports(path,inputs,outputs)
for j=1:numel(inputs)
    b(path,'simulink/Ports & Subsystems/In1',inputs{j},[10 60*j 40 60*j+14],'Port',num2str(j));
end
for j=1:numel(outputs)
    b(path,'simulink/Ports & Subsystems/Out1',outputs{j},[1120 45*j 1150 45*j+14],'Port',num2str(j));
end
end
function b(path,library,name,position,varargin)
add_block(library,[path '/' name],'Position',position,varargin{:});
end
function constant(path,name,position,value)
b(path,'simulink/Sources/Constant',name,position,'Value',value,'SampleTime','1');
end
function source(path,name,variable,position)
b(path,'simulink/Sources/From Workspace',name,position, ...
    'VariableName',variable,'SampleTime','1','Interpolate','off','OutputAfterFinalValue','Holding final value');
end
function fn(path,name,position,function_name,folder)
b(path,'simulink/User-Defined Functions/MATLAB Function',name,position);
root=sfroot;
chart=root.find('-isa','Stateflow.EMChart','Path',[path '/' name]);
chart.Script=fileread(fullfile(folder,'blocks',[function_name '.m']));
end
function wire(path,src,dst,name)
h=add_line(path,src,dst,'autorouting','on');
if ~isempty(name), set_param(h,'Name',name); end
end
function collect(path,name,signals,position)
b(path,'simulink/Signal Routing/Mux',[name '_pack'],position,'Inputs',num2str(numel(signals)));
for j=1:numel(signals), wire(path,signals{j},sprintf('%s_pack/%d',name,j),''); end
b(path,'simulink/Sinks/To Workspace',name,position+[80 0 170 0], ...
    'VariableName',name,'SaveFormat','Array','MaxDataPoints','inf','SampleTime','1');
wire(path,[name '_pack/1'],[name '/1'],'');
end
function pack(path,name,signals,position,destination)
b(path,'simulink/Signal Routing/Mux',name,position,'Inputs',num2str(numel(signals)));
for j=1:numel(signals), wire(path,signals{j},sprintf('%s/%d',name,j),''); end
wire(path,[name '/1'],destination,'');
end
function decorate(path,title)
display=sprintf('disp(sprintf(''%s''));\n',title);
set_param(path,'Mask','on','MaskDisplay',display,'MaskIconOpaque','opaque-with-ports', ...
    'OpenFcn','open_system(gcb,''force'')');
end
