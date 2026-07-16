package monprojet.dao;
import java.sql.*;
public class CompagnonDao {
    public void lire() throws Exception {
        Connection c = DriverManager.getConnection("jdbc:mysql://x");
        Statement st = c.createStatement();
        ResultSet rs = st.executeQuery("SELECT * FROM compagnon WHERE id=" + 1);
    }
}
