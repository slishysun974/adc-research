using System;
using System.IO;

// Only offline source generation and fixed controls live here. Learner is Adc070.
public static class Adc071 {
    public sealed class SourceResult {
        public long SourceConversions,UnitCodes,UnitQ3Clips,UnitIntegerClips;
        public int MinimumUnit=4095,MaximumUnit=0;
    }
    public static SourceResult Source(string folder,string stem,string toneFile,ulong seed,int windows,bool ideal) {
        var tone=new double[30720];
        using(var input=new BinaryReader(File.OpenRead(toneFile))) {
            if(input.BaseStream.Length!=30720*8)throw new Exception("tone length");
            for(int j=0;j<tone.Length;j++)tone[j]=input.ReadDouble();
        }
        var result=new SourceResult();var unit=new double[]{1,1,1,1,1,1,1,1};
        using(var words=new BinaryWriter(File.Open(Path.Combine(folder,stem+"_words.bin"),FileMode.CreateNew)))
        using(var output=new BinaryWriter(File.Open(Path.Combine(folder,stem+"_unit_outputs.bin"),FileMode.CreateNew))) {
            for(long index=0;index<120L*windows;index++) {
                int d1=Adc057.Tag(seed,2,index),d2=Adc057.Tag(seed,3,index);
                var raw=Adc061.Plant(tone[index%tone.Length],d1,d2,ideal?1:.975,ideal?0:-.055,
                    ideal?1:.975,ideal?0:-.055,ideal?1:.98,ideal?0:-.04);
                int q1=(int)raw[0],q2=(int)raw[1],be=(int)raw[7];
                words.Write((sbyte)q1);words.Write((sbyte)q2);words.Write((sbyte)be);words.Write((byte)((d1>0?1:0)|(d2>0?2:0)));
                double y=Adc059.Correct(q1,q2,be,d1,d2,unit,3)[0];
                int code=(int)Math.Round(y,MidpointRounding.ToEven);
                if(y<0||y>4095)result.UnitQ3Clips++;if(code<0||code>4095)result.UnitIntegerClips++;
                output.Write((short)Math.Round(Math.Min(4095,Math.Max(0,y)),MidpointRounding.ToEven));
                result.MinimumUnit=Math.Min(result.MinimumUnit,code);result.MaximumUnit=Math.Max(result.MaximumUnit,code);
                result.SourceConversions++;result.UnitCodes++;
            }
        }
        return result;
    }
    public static void FixedReadout(string wordsFile,string outputFile,int[] codes,int limit) {
        var k=new double[8];for(int j=0;j<8;j++)k[j]=codes[j]/1024.0;
        using(var input=new BinaryReader(File.OpenRead(wordsFile)))
        using(var output=new BinaryWriter(File.Open(outputFile,FileMode.CreateNew))) {
            int n=limit<0?(int)(input.BaseStream.Length/4):limit;
            for(int i=0;i<n;i++) {
                int q1=input.ReadSByte(),q2=input.ReadSByte(),be=input.ReadSByte(),bits=input.ReadByte();
                double y=Adc059.Correct(q1,q2,be,(bits&1)==0?-1:1,(bits&2)==0?-1:1,k,3)[0];
                output.Write((int)Math.Round(y*8,MidpointRounding.ToEven));
                output.Write((int)Math.Round(y,MidpointRounding.ToEven));
                output.Write((int)Math.Round(Math.Min(4095,Math.Max(0,y)),MidpointRounding.ToEven));
            }
        }
    }
    public static int InvalidInputs() {
        int rejected=0;
        foreach(bool ideal in new bool[]{false,true})foreach(double x in new double[]{1,-1-1.0/2048})
        foreach(int d1 in new int[]{-1,1})foreach(int d2 in new int[]{-1,1}) {
            try { Adc061.Plant(x,d1,d2,ideal?1:.975,ideal?0:-.055,ideal?1:.975,ideal?0:-.055,ideal?1:.98,ideal?0:-.04); }
            catch(Exception) { rejected++;continue; }
            throw new Exception("invalid source accepted");
        }
        return rejected;
    }
}
