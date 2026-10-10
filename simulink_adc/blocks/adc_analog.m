function y = adc_analog(z,p)
%#codegen
% z = actual_gain * residue_preamp. p: mode,a,b,domain,ideal5,distorted5.
mode = p(1);
if mode == 0
    y = z;
elseif mode == 1
    assert(abs(z) <= p(4));
    y = p(2)*z + p(3)*z^3;
else
    magnitude = abs(z);
    assert(magnitude <= p(9));
    index = 1;
    for j=2:5
        if magnitude >= p(4+j)
            index = j;
        end
    end
    index = min(index,4);
    slope = (p(10+index)-p(9+index))/(p(5+index)-p(4+index));
    y = sign(z)*(p(9+index)+slope*(magnitude-p(4+index)));
end
end
