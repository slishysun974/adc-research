function [raw,centered,channel,quantized] = adc_sar(u,n)
%#codegen
% Preserve Python's (u-low)/step order at floating boundary neighbors.
raw = min(max(floor((u-(-1))/(2/256)),0),255);
centered = raw-128;
channel = mod(n,4);
quantized = -1+(raw+0.5)*(2/256);
end
