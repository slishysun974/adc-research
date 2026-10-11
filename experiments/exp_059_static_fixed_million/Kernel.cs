using System;
using System.IO;
using System.Collections.Generic;

// Experiment-local acceleration. Plant and floating reference are frozen EXP-057.
public static class Adc059 {
    public static void Edges(string folder) {
        using(var output=new BinaryWriter(File.Open(Path.Combine(folder,"pwl_edges.bin"),FileMode.CreateNew)))
        foreach(int width in new int[]{32,128})
        foreach(int[] codes in new int[][]{new int[]{1024,1024,1024,1024},new int[]{1025,1043,1067,1101},new int[]{0,2047,1024,1}}) {
            var k=new double[4];for(int j=0;j<4;j++)k[j]=codes[j]/1024.0;
            for(int raw=-32*width;raw<32*width;raw++) {
                output.Write((double)width);output.Write(raw/8.0);foreach(double v in k)output.Write(v);
                output.Write(Pwl(raw/8.0,k,0,width));
            }
        }
        using(var output=new BinaryWriter(File.Open(Path.Combine(folder,"round_edges.bin"),FileMode.CreateNew)))
        foreach(long denominator in new long[]{2,4,125,4096})
        foreach(long numerator in new long[]{-6144,-4097,-4096,-2049,-2048,-2047,-5,-3,-1,0,1,3,5,2047,2048,2049,4096,4097,6144}) {
            output.Write(numerator);output.Write(denominator);output.Write(Rn(numerator,denominator));
        }
    }
    public static long Rn(long n,long d) {
        long q=n/d,r=n%d;
        if(Math.Abs(r)*2>d || (Math.Abs(r)*2==d && q%2!=0))q+=Math.Sign(n);
        return q;
    }
    public static double Q3(double v) { return Math.Round(v*8,MidpointRounding.ToEven)/8; }
    public static double[] Effective(double[] hidden,int mode) {
        var k=(double[])hidden.Clone();
        if(mode>=2)for(int j=0;j<8;j++)k[j]=Math.Min(2047,Math.Max(0,Math.Round(k[j]*1024,MidpointRounding.ToEven)))/1024;
        return k;
    }
    public static double Pwl(double raw,double[] k,int offset,double width) {
        if(raw < -4*width || raw>=4*width || Double.IsNaN(raw))throw new Exception("illegal raw");
        double mag=Math.Abs(raw);int j=Math.Min((int)(mag/width),3);
        double sum=0;for(int i=0;i<j;i++)sum+=k[offset+i];
        double value=Q3(width*sum)+Q3((mag-j*width)*k[offset+j]);
        return raw<0?-value:raw==0?0:value;
    }
    // Digital words and state only; no analog parameters or ideal input.
    public static double[] Correct(int q1,int q2,int backend,int d1,int d2,double[] k,int mode) {
        if(mode==0)return Adc057.Correct(q1,q2,backend,d1,d2,k);
        double p2=Pwl(backend,k,4,32),r1=128*q2+p2-16*d2;
        double y1=Pwl(r1,k,0,128)-64*d1;
        return new double[]{2048+512*q1+y1,y1,p2-16*d2,r1};
    }
    public sealed class Context {
        public double[] Hidden=new double[]{1,1,1,1,1,1,1,1};
        public long[] Acc=new long[]{4194304,4194304,4194304,4194304,4194304,4194304,4194304,4194304};
        public double[] K,Sums=new double[8];
        public long[] Gates=new long[8],Basis=new long[8],Both=new long[8],ZeroRequest=new long[8],HiddenChanged=new long[8],ExportChanged=new long[8];
        public long Clips=0,OutputClips=0;
        public void Begin(int mode) { K=Effective(Hidden,mode); }
    }
    public static void Products(Context c,int q1,int q2,int backend,int d1,int d2,int mode) {
        var y=Correct(q1,q2,backend,d1,d2,c.K,mode);
        if(y[0]<0||y[0]>4095)c.OutputClips++;
        for(int bank=0;bank<2;bank++) {
            double width=bank==0?128:32,local=y[bank+1],dd=bank==0?64*d1:16*d2;
            double raw=Math.Abs(bank==0?y[3]:backend),sum=0;
            for(int j=0;j<4;j++) {
                double threshold=mode==0?width*sum:Q3(width*sum);
                bool gate=j==0||Math.Abs(local)>=threshold,support=raw>j*width;
                if(gate){c.Sums[4*bank+j]+=dd*local;c.Gates[4*bank+j]++;}
                if(support)c.Basis[4*bank+j]++;
                if(gate&&support)c.Both[4*bank+j]++;
                sum+=c.K[4*bank+j];
            }
        }
    }
    public static void Commit(Context c,int mode,int multiplier) {
        int[] num={1,3,6,12};
        for(int j=0;j<8;j++) {
            double before=c.Hidden[j],requested;
            if(mode==3) {
                // Q3 local*dither sums are exact integers in physical code units.
                if(c.Sums[j]!=(long)c.Sums[j])throw new Exception("noninteger product sum");
                long delta=Rn((j<4?-2L:-32L)*num[j%4]*multiplier*(long)c.Sums[j],125);
                if(delta==0)c.ZeroRequest[j]++;
                long next=c.Acc[j]+delta;
                if(next<0||next>2047L*4096)c.Clips++;
                c.Acc[j]=Math.Min(2047L*4096,Math.Max(0,next));
                requested=c.Acc[j]/4194304.0;
            } else {
                double step=num[j%4]/(j<4?262144000.0:16384000.0);
                requested=before-step*multiplier*c.Sums[j];
                if(c.Sums[j]==0)c.ZeroRequest[j]++;
                if(requested<0||requested>2)c.Clips++;
                requested=Math.Min(2,Math.Max(0,requested));
            }
            c.Hidden[j]=requested;
            if(before!=requested)c.HiddenChanged[j]++;
            double afterEffective=mode>=2?Math.Min(2047,Math.Max(0,Math.Round(requested*1024,MidpointRounding.ToEven)))/1024:requested;
            if(c.K[j]!=afterEffective)c.ExportChanged[j]++;
            c.Sums[j]=0;
        }
    }
    public sealed class Result {
        public string[] StateFiles;public string ProbeFile;
        public long[][] Gates,Basis,Both,ZeroRequest,HiddenChanged,ExportChanged;
        public long[] CoefficientClips,OutputClips;
        public long GeneratedSamples,PhysicalOverloads,BaselineStatesChecked;
        public int Windows,Selected,ProbeWindows;
    }
    public static Result Run(string folder,string baselineFolder,string name,ulong seed,double a1,double b1,double a2,double b2,
                            int windows,int selected,int multiplier,int[] probeWindows,bool checkBaseline) {
        string stem=Path.Combine(folder,name+"_"+seed);
        string[] states={stem+"_q3.bin",stem+"_export.bin",stem+"_q22.bin"};
        string probes=stem+"_probes.bin";
        var c=new Context[]{new Context(),new Context(),new Context(),new Context()};
        var keep=new HashSet<int>(probeWindows);long over=0,matched=0;int probeCount=0;
        BinaryReader reference=checkBaseline?new BinaryReader(File.OpenRead(Path.Combine(baselineFolder,name+"_"+seed+"_sar8.bin"))):null;
        using(var s1=new BinaryWriter(File.Open(states[0],FileMode.CreateNew)))
        using(var s2=new BinaryWriter(File.Open(states[1],FileMode.CreateNew)))
        using(var s3=new BinaryWriter(File.Open(states[2],FileMode.CreateNew)))
        using(var audit=new BinaryWriter(File.Open(probes,FileMode.CreateNew))) {
            var streams=new BinaryWriter[]{null,s1,s2,s3};
            try {
                for(int mode=1;mode<4;mode++)foreach(double k in c[mode].Hidden)streams[mode].Write(k);
                if(reference!=null)foreach(double k in c[0].Hidden){if(reference.ReadDouble()!=k)throw new Exception("baseline initial mismatch");matched++;}
                for(int w=0;w<windows;w++) {
                    bool save=keep.Contains(w);
                    for(int mode=0;mode<4;mode++)c[mode].Begin(mode);
                    if(save){audit.Write((double)w);foreach(var ctx in c)foreach(double k in ctx.Hidden)audit.Write(k);probeCount++;}
                    for(int n=0;n<selected;n++) {
                        long index=120L*w+n;double x=Adc057.Input(seed,index);
                        int d1=Adc057.Tag(seed,2,index),d2=Adc057.Tag(seed,3,index);
                        var raw=Adc057.Plant(x,d1,d2,a1,b1,a2,b2);
                        if(x< -1||x>=1||raw[2]< -1||raw[2]>=1||raw[3]< -1||raw[3]>=1)over++;
                        // Original reference uses original threshold accumulation order.
                        var original=new Adc057.Context { K=c[0].Hidden,Sums=c[0].Sums,Gates=c[0].Gates,Basis=c[0].Basis,Both=c[0].Both };
                        Adc057.Products(original,(int)raw[0],(int)raw[1],raw[5],d1,d2);
                        c[0].OutputClips+=original.OutputClips;
                        for(int mode=1;mode<4;mode++)Products(c[mode],(int)raw[0],(int)raw[1],(int)raw[5],d1,d2,mode);
                        if(save){
                            audit.Write(x);audit.Write((double)d1);audit.Write((double)d2);foreach(double v in raw)audit.Write(v);
                            for(int mode=0;mode<4;mode++) {
                                var value=Correct((int)raw[0],(int)raw[1],(int)raw[5],d1,d2,c[mode].K,mode);
                                foreach(double v in value)audit.Write(v);
                                int gm=0,bm=0;
                                for(int bank=0;bank<2;bank++) {
                                    double width=bank==0?128:32,sum=0,threshold=0;
                                    for(int j=0;j<4;j++) {
                                        double t=mode==0?threshold:Q3(width*sum);
                                        if(j==0||Math.Abs(value[bank+1])>=t)gm|=1<<(4*bank+j);
                                        if(Math.Abs(bank==0?value[3]:raw[5])>j*width)bm|=1<<(4*bank+j);
                                        sum+=c[mode].K[4*bank+j];threshold+=width*c[mode].K[4*bank+j];
                                    }
                                }
                                audit.Write((double)gm);audit.Write((double)bm);
                            }
                        }
                    }
                    if(save)foreach(var ctx in c)foreach(double s in ctx.Sums)audit.Write(s);
                    for(int mode=0;mode<4;mode++) {
                        Commit(c[mode],mode,multiplier);
                        if(mode>0)foreach(double k in c[mode].Hidden)streams[mode].Write(k);
                        else if(reference!=null)foreach(double k in c[0].Hidden){if(reference.ReadDouble()!=k)throw new Exception("baseline state mismatch");matched++;}
                    }
                    if(save)foreach(var ctx in c)foreach(double k in ctx.Hidden)audit.Write(k);
                }
            } finally {if(reference!=null)reference.Dispose();}
        }
        var result=new Result{StateFiles=states,ProbeFile=probes,GeneratedSamples=(long)windows*selected,PhysicalOverloads=over,
            BaselineStatesChecked=matched,Windows=windows,Selected=selected,ProbeWindows=probeCount,
            Gates=new long[4][],Basis=new long[4][],Both=new long[4][],ZeroRequest=new long[4][],HiddenChanged=new long[4][],ExportChanged=new long[4][],
            CoefficientClips=new long[4],OutputClips=new long[4]};
        for(int m=0;m<4;m++){result.Gates[m]=c[m].Gates;result.Basis[m]=c[m].Basis;result.Both[m]=c[m].Both;
            result.ZeroRequest[m]=c[m].ZeroRequest;result.HiddenChanged[m]=c[m].HiddenChanged;result.ExportChanged[m]=c[m].ExportChanged;
            result.CoefficientClips[m]=c[m].Clips;result.OutputClips[m]=c[m].OutputClips;}
        return result;
    }
    public static double[] Tone(int[] q1,int[] q2,int[] be,int[] d1,int[] d2,double[] hidden,int mode,int selected,int multiplier,bool online) {
        var c=new Context{Hidden=(double[])hidden.Clone()};
        if(mode==3)for(int j=0;j<8;j++)c.Acc[j]=(long)Math.Round(hidden[j]*4194304);
        var output=new double[q1.Length];
        for(int start=0;start<q1.Length;start+=120) {
            c.Begin(mode);
            for(int n=start;n<start+120;n++) {
                output[n]=Correct(q1[n],q2[n],be[n],d1[n],d2[n],c.K,mode)[0];
                if(online&&n-start<selected)Products(c,q1[n],q2[n],be[n],d1[n],d2[n],mode);
            }
            if(online)Commit(c,mode,multiplier);
        }
        if(c.Clips!=0||c.OutputClips!=0)throw new Exception("tone clipping");
        return output;
    }
}
