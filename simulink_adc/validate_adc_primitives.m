function result=validate_adc_primitives(reference_folder)
folder=fileparts(mfilename('fullpath'));
addpath(fullfile(folder,'blocks'));
p=readmatrix(fullfile(reference_folder,'primitive_pwl.csv'));
g=readmatrix(fullfile(reference_folder,'primitive_gate.csv'));
s=readmatrix(fullfile(reference_folder,'primitive_sar.csv'));
max_pwl=0; max_gate=0; max_sar=0;
for j=1:size(p,1)
    [value,index]=adc_pwl(p(j,2),p(j,3:6),p(j,1),1);
    max_pwl=max(max_pwl,abs(value-p(j,7)));
    assert(index==p(j,8));
end
assert(max_pwl<=1e-12);
for j=1:size(g,1)
    [thresholds,gates,products]=adc_gate(g(j,2:5),g(j,1),g(j,6),g(j,7));
    max_gate=max(max_gate,max(abs([thresholds gates products]-g(j,8:19))));
    assert(isequal(gates,g(j,12:15)));
end
assert(max_gate<=1e-12);
for j=1:size(s,1)
    [raw,centered,channel,quantized]=adc_sar(s(j,1),s(j,2));
    max_sar=max(max_sar,max(abs([raw centered channel quantized]-s(j,3:6))));
end
assert(max_sar==0);
rejections=0;
for width=[32 128]
    for raw=[-4*width-eps(4*width) 4*width]
        try
            adc_pwl(raw,ones(1,4),width,1);
        catch
            rejections=rejections+1;
        end
    end
end
assert(rejections==4);
result=struct('passed',true,'pwl_probes',size(p,1),'gate_probes',size(g,1), ...
    'sar_probes',size(s,1),'rejected_invalid_pwl',rejections, ...
    'max_pwl_error',max_pwl,'max_gate_error',max_gate,'max_sar_error',max_sar);
fprintf('Primitive endpoints/gate equality/SAR: PASS\n');
end
