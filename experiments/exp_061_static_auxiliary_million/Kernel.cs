using System;
using System.IO;
using System.Collections.Generic;

// Local static acceleration; digital update is the frozen EXP-059 contract.
public static class Adc061 {
    public static double[] Plant(double x,int d1,int d2,double a1,double b1,double aa,double ba,double a2,double b2) {
        int q1=Adc057.Flash(x);
        double z1=4*(x-q1/4.0+d1/32.0);
        double m=a1*z1+b1*Math.Pow(z1,3),a=aa*z1+ba*Math.Pow(z1,3);
        int q2=Adc057.Flash(a);
        double z2=4*(m-q2/4.0+d2/32.0),r2=a2*z2+b2*Math.Pow(z2,3);
        if(x< -1||x>=1||Math.Abs(z1)>1||m< -1||m>=1||Math.Abs(z2)>1||r2< -1||r2>=1)
            throw new Exception("physical overload/domain");
        return new double[]{q1,q2,z1,m,a,z2,r2,Adc057.Quantize(r2)};
    }
    public sealed class Result {
        public long[] Gates,Basis,Both,ZeroRequest,HiddenChanged,ExportChanged;
        public long CoefficientClips,OutputClips,GeneratedSamples,PairedQ2Changes;
        public double MaximumObservedRA,MeanDelta2,MeanSquaredDelta2;
        public int Windows,Selected,ProbeWindows;
    }
    public static Result Run(string folder,string name,ulong seed,double a1,double b1,double aa,double ba,double a2,double b2,
        int windows,int selected,int multiplier,int[] probeWindows) {
        string stem=Path.Combine(folder,name+"_"+seed);
        var ctx=new Adc059.Context();var keep=new HashSet<int>(probeWindows);
        long changed=0;int probes=0;double ra=0,deltaSum=0,deltaSquare=0;
        using(var states=new BinaryWriter(File.Open(stem+"_q22.bin",FileMode.CreateNew)))
        using(var audit=new BinaryWriter(File.Open(stem+"_probes.bin",FileMode.CreateNew))) {
            foreach(double k in ctx.Hidden)states.Write(k);
            for(int w=0;w<windows;w++) {
                ctx.Begin(3);bool save=keep.Contains(w);
                if(save){audit.Write((double)w);foreach(double k in ctx.Hidden)audit.Write(k);probes++;}
                for(int j=0;j<selected;j++) {
                    long index=120L*w+j;double x=Adc057.Input(seed,index);
                    int d1=Adc057.Tag(seed,2,index),d2=Adc057.Tag(seed,3,index);
                    var raw=Plant(x,d1,d2,a1,b1,aa,ba,a2,b2);
                    if((int)raw[1]!=Adc057.Flash(raw[3]))changed++;
                    ra=Math.Max(ra,Math.Abs(raw[3]-raw[1]/4));
                    var value=Adc059.Correct((int)raw[0],(int)raw[1],(int)raw[7],d1,d2,ctx.K,3);
                    double delta=value[2]+16*d2-128*raw[5];deltaSum+=delta;deltaSquare+=delta*delta;
                    Adc059.Products(ctx,(int)raw[0],(int)raw[1],(int)raw[7],d1,d2,3);
                    if(save) {
                        audit.Write(x);audit.Write((double)d1);audit.Write((double)d2);foreach(double v in raw)audit.Write(v);
                        foreach(double v in value)audit.Write(v);
                        int gm=0,bm=0;
                        for(int bank=0;bank<2;bank++) {
                            double width=bank==0?128:32,sum=0,mag=Math.Abs(bank==0?value[3]:raw[7]);
                            for(int k=0;k<4;k++) {
                                if(k==0||Math.Abs(value[bank+1])>=Adc059.Q3(width*sum))gm|=1<<(4*bank+k);
                                if(mag>k*width)bm|=1<<(4*bank+k);
                                sum+=ctx.K[4*bank+k];
                            }
                        }
                        audit.Write((double)gm);audit.Write((double)bm);
                    }
                }
                if(save)foreach(double s in ctx.Sums)audit.Write(s);
                Adc059.Commit(ctx,3,multiplier);
                foreach(double k in ctx.Hidden)states.Write(k);
                if(save)foreach(double k in ctx.Hidden)audit.Write(k);
            }
        }
        long count=(long)windows*selected;
        return new Result{Gates=ctx.Gates,Basis=ctx.Basis,Both=ctx.Both,ZeroRequest=ctx.ZeroRequest,
            HiddenChanged=ctx.HiddenChanged,ExportChanged=ctx.ExportChanged,CoefficientClips=ctx.Clips,OutputClips=ctx.OutputClips,
            GeneratedSamples=count,PairedQ2Changes=changed,MaximumObservedRA=ra,MeanDelta2=deltaSum/count,
            MeanSquaredDelta2=deltaSquare/count,Windows=windows,Selected=selected,ProbeWindows=probes};
    }
}
