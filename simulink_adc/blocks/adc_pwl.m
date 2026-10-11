function [y,index] = adc_pwl(raw,coefficients,width,enabled)
%#codegen
if enabled == 0
    y = raw;
    index = -1;
    return
end
assert(raw >= -4*width && raw < 4*width);
magnitude = abs(raw);
index = min(floor(magnitude/width),3);
local = magnitude-index*width;
offset = 0;
for j=1:4
    if j <= index
        offset = offset+width*coefficients(j);
    end
end
y = sign(raw)*(offset+coefficients(index+1)*local);
end
