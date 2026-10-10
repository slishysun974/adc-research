function [thresholds,gates,products] = adc_gate(coefficients,width,dither,local)
%#codegen
thresholds = zeros(1,4);
gates = ones(1,4);
products = zeros(1,4);
cumulative = 0;
for j=1:4
    if j > 1
        cumulative = cumulative+width*coefficients(j-1);
        thresholds(j) = cumulative;
        gates(j) = double(abs(local) >= cumulative);
    end
    if gates(j) == 1
        products(j) = dither*local;
    end
end
end
