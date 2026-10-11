function [q,region,thermometer] = adc_flash(u,thresholds)
%#codegen
% Python bisect_right: equality belongs to the higher region.
thermometer = zeros(1,8);
region = 0;
for j=1:8
    thermometer(j) = double(u >= thresholds(j));
    region = region + thermometer(j);
end
q = region - 4;
end
