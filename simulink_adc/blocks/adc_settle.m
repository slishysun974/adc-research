function [y,start] = adc_settle(target,previous,p)
%#codegen
% mode0 static; mode1/2 one-phase; mode3 tracking+amplification.
if p(1) == 0
    start = 0;
    y = target;
elseif p(1) == 3
    start = p(4) + p(3)*(previous-p(4));
    y = target + p(2)*(start-target);
else
    start = previous;
    y = (1-p(2))*target + p(2)*previous;
end
end
