function [nominal,mismatch,actual,dither] = adc_cdac(q,tag,levels,errors,amplitude)
%#codegen
nominal = levels(q+5);
mismatch = errors(q+5);
actual = nominal + mismatch;
dither = tag * amplitude; % tag=0 represents Python None (disabled).
end
