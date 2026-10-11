function verify_adc_performance_metrics(run_folder)
% Independent MATLAB FFT check of offline Python SNDR/SFDR calculations.
p=jsondecode(fileread(fullfile(run_folder,'protocol.json')));
manifest=jsondecode(fileread(fullfile(run_folder,'reference','manifest.json')));
summary=jsondecode(fileread(fullfile(run_folder,'summary.json')));
checks=struct('conversions',{},'format',{},'sndr_error_db',{},'sfdr_error_db',{});
harmonic_checks=struct('conversions',{},'format',{},'level_error_db',{},'thd_error_db',{});
for j=1:numel(manifest.cases)
    e=manifest.cases(j);
    if ~strcmp(e.kind,'test'), continue; end
    h=fopen(fullfile(run_folder,'simulink',[e.name '_digital_trace.bin']),'r','ieee-le');
    assert(h>=0); data=fread(h,[13 e.samples],'double=>double').'; fclose(h);
    reference=summary.checkpoints.(sprintf('x%d',e.offset));
    for format={'floating','integer'}
        values=data(:,1);
        if strcmp(format{1},'integer'), values=min(max(floor(values+.5),0),4095); end
        n=numel(values); values=values-mean(values);
        f=fft(values)/n;
        power=abs(f(1:n/2+1)).^2; power(2:end-1)=2*power(2:end-1); power(1)=0;
        fund=power(p.test.fundamental_bin+1);
        residual=sum(power)-fund;
        power(p.test.fundamental_bin+1)=0;
        sndr=10*log10(fund/residual); sfdr=10*log10(fund/max(power));
        expected=reference.(format{1});
        d1=abs(sndr-expected.sndr_db); d2=abs(sfdr-expected.sfdr_dbc);
        assert(d1<1e-6 && d2<1e-6,'MATLAB/Python FFT metrics differ');
        checks(end+1)=struct('conversions',e.offset,'format',format{1}, ...
            'sndr_error_db',d1,'sfdr_error_db',d2); %#ok<AGROW>
        if isfield(p,'harmonic_analysis') && (e.offset==0 || e.offset==p.training.conversions)
            if strcmp(format{1},'floating'), name='harmonics.csv'; else, name='harmonics_integer.csv'; end
            rows=readmatrix(fullfile(run_folder,'figures',name));
            b=mod(rows(:,1)*p.test.fundamental_bin,n);
            b=min(b,n-b);
            assert(isequal(b,rows(:,2)),'Harmonic folding differs');
            if e.offset==0, column=4; thd_field='thd_before_db';
            else, column=5; thd_field='thd_after_db'; end
            dbfs=10*log10(max(power(b+1)/(2048^2/2),1e-200));
            dbc=10*log10(max(power(b+1)/fund,1e-200));
            level_error=max([abs(dbfs-rows(:,column));abs(dbc-rows(:,column+2))]);
            thd=10*log10(sum(power(b+1))/fund);
            thd_error=abs(thd-summary.harmonic_analysis.(format{1}).(thd_field));
            assert(level_error<1e-6 && thd_error<1e-6,'Harmonic metrics differ');
            harmonic_checks(end+1)=struct('conversions',e.offset,'format',format{1}, ...
                'level_error_db',level_error,'thd_error_db',thd_error); %#ok<AGROW>
        end
    end
end
result=struct('passed',true,'tolerance_db',1e-6,'checks',checks, ...
    'max_sndr_error_db',max([checks.sndr_error_db]), ...
    'max_sfdr_error_db',max([checks.sfdr_error_db]));
if ~isempty(harmonic_checks)
    result.harmonic_checks=harmonic_checks;
    result.max_harmonic_level_error_db=max([harmonic_checks.level_error_db]);
    result.max_harmonic_thd_error_db=max([harmonic_checks.thd_error_db]);
end
h=fopen(fullfile(run_folder,'metrics_verification.json'),'w','n','UTF-8');
fprintf(h,'%s\n',jsonencode(result,PrettyPrint=true)); fclose(h);
fprintf('Independent MATLAB FFT metrics verified: SNDR max %.3g dB, SFDR max %.3g dB.\n', ...
    result.max_sndr_error_db,result.max_sfdr_error_db);
end
