function [y,target,start] = adc_auxiliary(preamp,main,previous,p)
%#codegen
% p: mode,rho,offset,main_gain,aux_gain,a,b,domain,amp,track,track_target.
if p(1) == 0 || p(1) == 1
    target = p(2)*main+p(3);
    start = 0;
    y = target;
elseif p(1) == 2
    target = p(2)*p(4)*preamp+p(3);
    start = previous;
    y = (1-p(9))*target+p(9)*previous;
else
    z = p(5)*preamp;
    assert(abs(z) <= p(8));
    target = p(6)*z+p(7)*z^3;
    start = p(11)+p(10)*(previous-p(11));
    y = target+p(9)*(start-target);
end
end
